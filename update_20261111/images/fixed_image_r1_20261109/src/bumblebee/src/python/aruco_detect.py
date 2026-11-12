#!/home/lb/opencv47_venv/bin/python3
# Copyright 2026 FutureLab
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
aruco_detect.py — Python ArUco detection + map pose node for Bumblebee.

Replaces C++ aruco_detect AND aruco_map from aruco_pose package.
Subscribes directly to image_raw (rgb8) and camera_info without image_transport,
avoiding QoS/sync issues with the C++ nodes.

Publishes:
  - markers (aruco_pose/MarkerArray) — detected markers with poses
  - debug (sensor_msgs/Image) — debug image with drawn markers
  - map_pose (geometry_msgs/PoseWithCovarianceStamped) — camera pose in map frame
  - map_image (sensor_msgs/Image) — top-down map visualization
  - /tf — marker transforms + aruco_map_detected frame
"""

import collections
import math
import numpy as np
import cv2
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
from sensor_msgs.msg import Image, CameraInfo
from std_msgs.msg import Int32, Bool
from mavros_msgs.msg import State
from geometry_msgs.msg import TransformStamped, Pose, Point, Quaternion, PoseWithCovarianceStamped
from tf2_ros import TransformBroadcaster, Buffer, TransformListener
from aruco_pose.msg import MarkerArray as ArucoMarkerArray, Marker as ArucoMarker


def rvec_to_quaternion(rvec):
    """Convert Rodrigues rotation vector to quaternion (x, y, z, w)."""
    R, _ = cv2.Rodrigues(rvec)
    return rotation_matrix_to_quaternion(R)


def rotation_matrix_to_quaternion(R):
    """Convert 3x3 rotation matrix to quaternion (x, y, z, w)."""
    tr = R[0, 0] + R[1, 1] + R[2, 2]
    if tr > 0:
        s = 0.5 / np.sqrt(tr + 1.0)
        w = 0.25 / s
        x = (R[2, 1] - R[1, 2]) * s
        y = (R[0, 2] - R[2, 0]) * s
        z = (R[1, 0] - R[0, 1]) * s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = 2.0 * np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s
    return x, y, z, w


def quaternion_to_rotation_matrix(x, y, z, w):
    """Convert quaternion to 3x3 rotation matrix."""
    R = np.array([
        [1 - 2*(y*y + z*z), 2*(x*y - z*w), 2*(x*z + y*w)],
        [2*(x*y + z*w), 1 - 2*(x*x + z*z), 2*(y*z - x*w)],
        [2*(x*z - y*w), 2*(y*z + x*w), 1 - 2*(x*x + y*y)],
    ], dtype=np.float64)
    return R


def yaw_from_quat(q):
    """Yaw angle (rad) from quaternion (x, y, z, w)."""
    qx, qy, qz, qw = q
    siny_cosp = 2.0 * (qw * qz + qx * qy)
    cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
    return math.atan2(siny_cosp, cosy_cosp)


def wrap_pi(a):
    """Wrap angle to (-pi, pi]."""
    return math.atan2(math.sin(a), math.cos(a))


# Tuning constants for the "external" coordinate-system mode.
#
# Single-marker poses are inherently ambiguous (IPPE planar mirror flip), so
# the gate publishes vision pose only when geometry is reliable:
#   - >=2 markers visible (mirror flip impossible — markers' baseline locks orientation), OR
#   - one large, near-centred marker (geometry close enough to disambiguate via marker normal).
# yaw_world (a low-pass over the world yaw observed during multi-marker windows) is then
# used to pick the correct IPPE candidate when only a single marker remains.
_QUORUM_MIN_MARKERS         = 2
# Single-marker geometry gate: physical-size threshold accommodates marker id=0 (0.19m),
# while pixel-size + reprojection-error checks still throw out poor IPPE solves.
_SINGLE_MARKER_MIN_LEN_M    = 0.18
_SINGLE_MARKER_MAX_NDIST    = 0.40     # normalized distance from image centre (0..1)
_SINGLE_MARKER_MIN_PIXELS   = 50       # max-side bbox in pixels (apparent quality)
_SINGLE_MARKER_MAX_REPROJ   = 14.0     # floor of the size-adaptive limit below
# 2026-06-10: reproj error of a CORRECT solve scales with marker apparent size
# (fractional corner error is ~5-11% of side on this camera: 5x row upsample +
# strong OV5647 distortion). Log evidence: good big markers pixel=256-277 hit
# err=14-30px (err/pixel 0.055-0.110) while a genuine IPPE flip was err/pixel
# 4.29 — a flat 14px gate rejects valid oblique views for 10+ s and unlocks
# yaw_world. Limit = min(CAP, max(REPROJ, FRAC * pixel_size)).
_SINGLE_MARKER_REPROJ_FRAC  = 0.12     # max err as fraction of marker pixel size
_SINGLE_MARKER_REPROJ_CAP   = 60.0     # absolute ceiling regardless of size
_VEL_LIMIT_MPS              = 2.5      # reject pose if implied speed exceeds this (multi)
_VEL_LIMIT_SINGLE_MPS       = 1.0      # 2026-06-05: relaxed back from 0.7
_OUTLIER_PAUSE_S            = 0.5      # quiet window after 3 consecutive outliers
# Low-pass smoothing applied to PUBLISHED pose only when n_used == 1. With
# alpha=0.3 at ~6 Hz publish rate, the time-constant is ~0.5 s — enough to
# smooth IPPE corner-jitter while still letting the drone track real motion.
# Multi-marker frames bypass the filter (full responsiveness), so flight
# scripts that work with several markers in view see no extra latency.
_SINGLE_MARKER_LP_ALPHA     = 0.3      # 2026-06-05: REVERTED to original (0.2 not helpful, may add lag)
_YAW_LP_ALPHA               = 0.20
_YAW_LOCK_WINDOW_S          = 1.5      # continuous multi-marker time before yaw is "locked"
# Single-marker fallback: lock yaw_world after a longer window of consistent observation.
# Spread test rejects the case where IPPE keeps oscillating between flip candidates.
_YAW_LOCK_SINGLE_WINDOW_S   = 3.0      # 2026-06-05: REVERTED to original
_YAW_LOCK_SINGLE_SPREAD_RAD = math.radians(8.0)  # 2026-06-05: relaxed back from 5
_YAW_LOCK_SINGLE_SAMPLES    = 10
_YAW_LOCK_SINGLE_MAX_DEV    = math.radians(30.0)  # observation rejected if too far from current yaw_world
# 2026-06-10: when the two IPPE candidates have clearly different reprojection
# errors the geometry is unambiguous — trust the min-error solve instead of the
# warm-start / yaw heuristics (which can perpetuate a stale flip). Heuristics
# are only consulted when errors are within this ratio (near-frontal views).
_IPPE_AMBIG_RATIO           = 1.5
_YAW_DISAMBIG_TOL_RAD       = math.pi / 6.0   # 30 deg — IPPE candidate must land within
_YAW_RESET_GAP_S            = 5.0      # vision silent for this long → drop the lock


class ArucoDetectNode(Node):
    def __init__(self):
        super().__init__('aruco_detect')

        # Parameters
        self.declare_parameter('dictionary', 1)
        self.declare_parameter('length', 0.15)
        self.declare_parameter('estimate_poses', True)
        self.declare_parameter('send_tf', True)
        self.declare_parameter('use_map_markers', True)
        self.declare_parameter('min_marker_perimeter_rate', 0.03)
        self.declare_parameter('corner_refinement_method', 3)  # 3 = APRILTAG (best subpixel)
        self.declare_parameter('corner_refinement_win_size', 9)
        self.declare_parameter('adaptive_thresh_win_size_min', 3)
        self.declare_parameter('adaptive_thresh_win_size_max', 101)
        self.declare_parameter('adaptive_thresh_win_size_step', 10)
        self.declare_parameter('polygonal_approx_accuracy_rate', 0.05)
        self.declare_parameter('max_erroneous_bits_in_border_rate', 0.04)
        # 2026-06-10: 0.6 -> 1.0 (full dictionary correction capability). The
        # drone's own shadow across a marker corrupts data bits; bench test on
        # the shadowed id0: errCorr=1.0 decodes 5/5 frames with ZERO false IDs,
        # while relaxing maxErroneousBitsInBorderRate instead produced phantom
        # ids and did not recover id0.
        self.declare_parameter('error_correction_rate', 1.0)
        self.declare_parameter('perspective_remove_ignored_margin_per_cell', 0.20)
        self.declare_parameter('min_otsu_std_dev', 3.0)
        self.declare_parameter('detect_inverted_marker', False)
        self.declare_parameter('min_distance_to_border', 1)
        self.declare_parameter('use_clahe', True)
        self.declare_parameter('clahe_clip_limit', 3.0)
        self.declare_parameter('clahe_tile_grid', 8)
        self.declare_parameter('gamma', 0.8)
        self.declare_parameter('refine_with_board', False)
        self.declare_parameter('frame_id_prefix', 'aruco_')
        self.declare_parameter('enabled', True)
        self.declare_parameter('map_frame_id', 'aruco_map_detected')
        self.declare_parameter('map_file', '')
        # Flight-state gate: ArUco is only needed for autonomous (OFFBOARD)
        # missions. Outside that, detection needlessly pins ~2 cores AND the node
        # keeps ingesting the 24 Hz camera stream (the real CPU cost), which
        # starves the ROS graph -> dashboard/telemetry freeze + false red LED.
        # When gated idle we DESTROY the image subscription entirely, so no
        # frames are delivered and CPU drops to ~0. The subscription is recreated
        # the instant the FCU arms / enters OFFBOARD (full_rate_when_armed keeps
        # it up for the whole armed window so mid-flight OFFBOARD entry never
        # lacks vision). Set gate_by_flight_state=False to always detect.
        self.declare_parameter('gate_by_flight_state', True)
        self.declare_parameter('full_rate_when_armed', True)
        # Detection-boost params (no calibration change)
        self.declare_parameter('use_unsharp', True)
        self.declare_parameter('unsharp_sigma', 1.0)
        self.declare_parameter('unsharp_amount', 0.6)
        # Hard shadow boundaries can be amplified by CLAHE's tile-local stretch
        # until marker interiors stop decoding; retry the gamma-only image on
        # detection-empty frames (every 2nd, bounded CPU). Experimental,
        # default off — enable for bench testing only.
        self.declare_parameter('retry_no_clahe', False)
        self.declare_parameter('aruco3_downscale_every_n', 4)  # 0 disables
        self.declare_parameter('track_roi_expand', 1.5)
        self.declare_parameter('track_roi_min_px', 60)
        self.declare_parameter('track_sweep_min', 3)
        self.declare_parameter('track_sweep_max', 21)
        self.declare_parameter('track_sweep_step', 6)
        self.declare_parameter('track_keepalive_frames', 3)
        # OpenCV >=4.7 ArucoDetector knobs
        self.declare_parameter('use_aruco3_detection', True)
        # 2026-06-10: 16 -> 12, markers ~25% farther survive Aruco3 pyramid
        # filtering (altitude reach). Revert to 16 if publish rate drops < 6 Hz.
        self.declare_parameter('aruco3_min_canonical_img_side', 12)
        self.declare_parameter('aruco3_min_marker_length_ratio', 0.0)
        self.declare_parameter('april_tag_deglitch', True)
        self.declare_parameter('refine_min_rep_distance', 10.0)
        self.declare_parameter('refine_error_correction_rate', 3.0)
        self.declare_parameter('refine_check_all_orders', True)

        dict_id = self.get_parameter('dictionary').value
        self.default_length = self.get_parameter('length').value
        self.estimate_poses = self.get_parameter('estimate_poses').value
        self.send_tf = self.get_parameter('send_tf').value
        self.use_map_markers = self.get_parameter('use_map_markers').value
        self.frame_id_prefix = self.get_parameter('frame_id_prefix').value
        self.enabled = self.get_parameter('enabled').value
        # Flight-state gate config + live FCU state (updated by _state_cb).
        self.gate_by_flight_state = bool(self.get_parameter('gate_by_flight_state').value)
        self.full_rate_when_armed = bool(self.get_parameter('full_rate_when_armed').value)
        self._fcu_mode = ''
        self._fcu_armed = False
        self._image_sub = None      # created/destroyed by _apply_detection_gate
        self._img_qos = None        # stored so the sub can be recreated
        self.map_frame_id = self.get_parameter('map_frame_id').value

        map_file = self.get_parameter('map_file').value

        # ArUco setup — OpenCV >=4.7 ArucoDetector API
        self.aruco_dict = cv2.aruco.getPredefinedDictionary(dict_id)
        self.aruco_params = cv2.aruco.DetectorParameters()
        self.aruco_params.cornerRefinementMethod = self.get_parameter('corner_refinement_method').value
        self.aruco_params.cornerRefinementWinSize = self.get_parameter('corner_refinement_win_size').value
        self.aruco_params.minMarkerPerimeterRate = self.get_parameter('min_marker_perimeter_rate').value
        self.aruco_params.adaptiveThreshWinSizeMin = self.get_parameter('adaptive_thresh_win_size_min').value
        self.aruco_params.adaptiveThreshWinSizeMax = self.get_parameter('adaptive_thresh_win_size_max').value
        self.aruco_params.adaptiveThreshWinSizeStep = self.get_parameter('adaptive_thresh_win_size_step').value
        self.aruco_params.polygonalApproxAccuracyRate = self.get_parameter('polygonal_approx_accuracy_rate').value
        self.aruco_params.maxErroneousBitsInBorderRate = self.get_parameter('max_erroneous_bits_in_border_rate').value
        self.aruco_params.errorCorrectionRate = self.get_parameter('error_correction_rate').value
        # Native Aruco3 detection — extends usable range at altitude.
        # When ON, minSideLengthCanonicalImg is the per-pyramid-level lower bound
        # for a marker to survive contour filtering (smaller -> see farther markers
        # but more CPU). minMarkerLengthRatioOriginalImg=0 disables the size hint
        # ratio so very small markers can still be found.
        self.aruco_params.useAruco3Detection = bool(
            self.get_parameter('use_aruco3_detection').value)
        self.aruco_params.minSideLengthCanonicalImg = int(
            self.get_parameter('aruco3_min_canonical_img_side').value)
        self.aruco_params.minMarkerLengthRatioOriginalImg = float(
            self.get_parameter('aruco3_min_marker_length_ratio').value)
        # Temporal April-Tag style deglitch — drops one-frame phantom detections.
        # Cheap insurance against false-positives that would otherwise trip the
        # velocity gate in vpe_fix.
        self.aruco_params.aprilTagDeglitch = 1 if bool(
            self.get_parameter('april_tag_deglitch').value) else 0
        # Robustness to oblique angles, shadow, edge-of-frame, contrast inversion
        for attr, name in (
            ('perspectiveRemoveIgnoredMarginPerCell', 'perspective_remove_ignored_margin_per_cell'),
            ('minOtsuStdDev',                         'min_otsu_std_dev'),
            ('detectInvertedMarker',                  'detect_inverted_marker'),
            ('minDistanceToBorder',                   'min_distance_to_border'),
        ):
            if hasattr(self.aruco_params, attr):
                setattr(self.aruco_params, attr, self.get_parameter(name).value)

        # RefineParameters — controls cv2.aruco.refineDetectedMarkers (Aruco map
        # recovery): minRepDistance is the search radius for unmatched corners,
        # errorCorrectionRate scales bit-error tolerance during refinement.
        self.refine_params = cv2.aruco.RefineParameters(
            minRepDistance=float(self.get_parameter('refine_min_rep_distance').value),
            errorCorrectionRate=float(self.get_parameter('refine_error_correction_rate').value),
            checkAllOrders=bool(self.get_parameter('refine_check_all_orders').value),
        )

        # Main detector (full-frame pass).
        self.detector = cv2.aruco.ArucoDetector(
            self.aruco_dict, self.aruco_params, self.refine_params)

        # Gamma LUT (gamma < 1.0 lifts shadows before CLAHE)
        gamma = float(self.get_parameter('gamma').value)
        if gamma > 0 and abs(gamma - 1.0) > 1e-3:
            inv_g = 1.0 / gamma
            self.gamma_lut = np.array(
                [(((i / 255.0) ** inv_g) * 255.0) for i in range(256)],
                dtype=np.uint8)
        else:
            self.gamma_lut = None

        # CLAHE for shadow / uneven lighting robustness
        if self.get_parameter('use_clahe').value:
            clip = float(self.get_parameter('clahe_clip_limit').value)
            tile = int(self.get_parameter('clahe_tile_grid').value)
            self.clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(tile, tile))
        else:
            self.clahe = None

        # Unsharp mask (edge boost — fights motion blur and oblique-angle bit smear)
        self.use_unsharp = bool(self.get_parameter('use_unsharp').value)
        self.unsharp_sigma = float(self.get_parameter('unsharp_sigma').value)
        self.unsharp_amount = float(self.get_parameter('unsharp_amount').value)
        self.retry_no_clahe = bool(self.get_parameter('retry_no_clahe').value)

        # ── Block B: adaptive preprocessing presets (luma-classified) ──
        # Precompute 4 gamma LUTs and 4 CLAHE objects so image_cb only has to
        # look up the chosen preset; no per-frame allocation. Classifier
        # operates on the rectified (post-undistort) gray frame.
        def _build_lut(gamma_val):
            inv_g = 1.0 / float(gamma_val)
            return np.array(
                [(((i / 255.0) ** inv_g) * 255.0) for i in range(256)],
                dtype=np.uint8)
        lut_g06 = _build_lut(0.6)
        lut_g08 = _build_lut(0.8)
        lut_g14 = _build_lut(1.4)
        clahe_3_8 = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        clahe_2_8 = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        clahe_4_8 = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
        clahe_5_4 = cv2.createCLAHE(clipLimit=5.0, tileGridSize=(4, 4))
        self._preproc = {
            'NORMAL':       {'lut': lut_g08, 'clahe': clahe_3_8, 'unsharp_amount': 0.6},
            'BACKLIGHT':    {'lut': lut_g14, 'clahe': clahe_2_8, 'unsharp_amount': 0.3},
            'LOW_LIGHT':    {'lut': lut_g06, 'clahe': clahe_4_8, 'unsharp_amount': 0.8},
            'LOW_CONTRAST': {'lut': lut_g08, 'clahe': clahe_5_4, 'unsharp_amount': 1.0},
        }
        self._preproc_mode = 'NORMAL'
        self._preproc_mode_since = self.get_clock().now().nanoseconds * 1e-9

        # ── Block C: adaptive detector parameter profiles ──
        # NORMAL profile mirrors the existing self.aruco_params (already built).
        # SEARCHING profile widens adaptiveThresh sweep, enables inverted-marker
        # detection, lowers the Aruco3 canonical-size floor, and enables the
        # no-CLAHE retry pass. Triggered after N empty frames; reverts after
        # M successful detections.
        self._aruco_params_normal = self.aruco_params  # alias for clarity
        self._aruco_params_searching = cv2.aruco.DetectorParameters()
        # Copy everything from NORMAL first so we only diverge on the few
        # knobs the SEARCHING profile actually changes.
        for _attr in (
            'cornerRefinementMethod', 'cornerRefinementWinSize',
            'minMarkerPerimeterRate',
            'adaptiveThreshWinSizeMin', 'adaptiveThreshWinSizeMax',
            'adaptiveThreshWinSizeStep',
            'polygonalApproxAccuracyRate', 'maxErroneousBitsInBorderRate',
            'errorCorrectionRate',
            'useAruco3Detection', 'minSideLengthCanonicalImg',
            'minMarkerLengthRatioOriginalImg', 'aprilTagDeglitch',
            'perspectiveRemoveIgnoredMarginPerCell', 'minOtsuStdDev',
            'detectInvertedMarker', 'minDistanceToBorder',
        ):
            if (hasattr(self._aruco_params_searching, _attr)
                    and hasattr(self._aruco_params_normal, _attr)):
                setattr(self._aruco_params_searching, _attr,
                        getattr(self._aruco_params_normal, _attr))
        self._aruco_params_searching.adaptiveThreshWinSizeMax = 81
        self._aruco_params_searching.adaptiveThreshWinSizeStep = 8
        self._aruco_params_searching.detectInvertedMarker = True
        self._aruco_params_searching.minSideLengthCanonicalImg = 10
        # Track the original 'normal' retry_no_clahe setting so we can restore
        # it when leaving SEARCHING. SEARCHING force-enables the 4th pass.
        self._retry_no_clahe_normal = self.retry_no_clahe
        self._search_empty_count = 0
        self._search_success_count = 0
        self._search_profile = 'NORMAL'

        # Aruco3 emulation: every Nth frame run a second pass on a downscaled
        # image to recover markers too small for the full-res detector.
        self.aruco3_downscale_every_n = int(self.get_parameter('aruco3_downscale_every_n').value)
        self.frame_idx = 0

        # ROI tracking: search previous-frame marker bboxes first
        self.track_roi_expand = float(self.get_parameter('track_roi_expand').value)
        self.track_roi_min_px = int(self.get_parameter('track_roi_min_px').value)
        self.track_keepalive_frames = int(self.get_parameter('track_keepalive_frames').value)
        self.prev_marker_rois = []  # list of (x, y, w, h)
        self.frames_since_detection = 0

        # Narrow-sweep detector params for ROI passes (lighter CPU).
        # Aruco3 is OFF on this detector — inside a tracked ROI the marker is
        # known to be large enough that Aruco3's pyramid filtering only adds
        # cost. aprilTagDeglitch also OFF: ROI hits are deliberately speculative
        # and we don't want a single-frame ROI hit to be silently dropped.
        self.aruco_params_track = cv2.aruco.DetectorParameters()
        for attr in (
            'cornerRefinementMethod', 'cornerRefinementWinSize',
            'minMarkerPerimeterRate', 'polygonalApproxAccuracyRate',
            'maxErroneousBitsInBorderRate', 'errorCorrectionRate',
            'perspectiveRemoveIgnoredMarginPerCell', 'minOtsuStdDev',
            'detectInvertedMarker', 'minDistanceToBorder',
        ):
            if hasattr(self.aruco_params_track, attr) and hasattr(self.aruco_params, attr):
                setattr(self.aruco_params_track, attr, getattr(self.aruco_params, attr))
        self.aruco_params_track.adaptiveThreshWinSizeMin = int(self.get_parameter('track_sweep_min').value)
        self.aruco_params_track.adaptiveThreshWinSizeMax = int(self.get_parameter('track_sweep_max').value)
        self.aruco_params_track.adaptiveThreshWinSizeStep = int(self.get_parameter('track_sweep_step').value)
        self.detector_track = cv2.aruco.ArucoDetector(
            self.aruco_dict, self.aruco_params_track)

        # Board for refineDetectedMarkers (built lazily once map is loaded)
        self.refine_with_board = bool(self.get_parameter('refine_with_board').value)
        self.aruco_board = None

        # Camera calibration
        self.camera_matrix = None
        self.dist_coeffs = None
        self.fisheye = False  # set from CameraInfo: equidistant model / len(D)==4

        # Frame undistortion (Block D, 2026-06-17).
        # Built lazily from the first CameraInfo carrying valid K (and an image
        # large enough to know W/H). Once built, every image_cb runs cv2.remap
        # on `gray` *before* preprocessing/detect, and every PnP call uses
        # `self._K_undist` with zero distortion so we do not compensate twice.
        # If CameraInfo never arrives (or image_cb fires first), the pipeline
        # falls back to the original distorted path with (K, D).
        self._undistort_map1 = None
        self._undistort_map2 = None
        self._K_undist = None
        self._D_zero = np.zeros((1, 5), dtype=np.float64)
        self._undistort_size = None  # (W, H) of the map we already built
        self._undistort_logged = False

        # Map markers: {id: {'length': float, 'T': 4x4 transform matrix}}
        self.map_markers = {}

        # Load map file if provided
        if map_file:
            self._load_map_file(map_file)

        # QoS
        img_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1,
        )

        # Publishers
        self.markers_pub = self.create_publisher(ArucoMarkerArray, 'markers', 10)
        self.debug_pub = self.create_publisher(Image, 'debug', 10)
        self.map_pose_pub = self.create_publisher(PoseWithCovarianceStamped, 'map_pose', 10)
        self.map_image_pub = self.create_publisher(Image, 'map_image', 10)
        # Quality signals consumed by vpe_fix to gate EKF2_EV_CTRL during flight.
        # Absolute names so we do not depend on launch-time remappings; vpe_fix
        # subscribes to the same absolute topics.
        self.markers_used_pub = self.create_publisher(
            Int32, '/aruco_detect/markers_used', 10)
        self.yaw_locked_pub = self.create_publisher(
            Bool, '/aruco_detect/yaw_locked', 10)

        # External-coordinate-system gate state
        self._last_marker_tvec = {}            # marker_id -> last accepted tvec (3,)
        self._yaw_world = None                 # locked yaw of base_link in map frame, rad
        self._yaw_world_locked = False
        self._yaw_world_lock_start = None      # t_sec when current lock window began
        self._yaw_lock_via_single = False      # True if current lock came from single-marker path
        self._yaw_single_samples = []          # rolling yaw observations for single-marker path
        self._last_pub_pos = None              # last RAW (pre-smoothing) pose for velocity gate
        self._last_pub_t = None                # t_sec
        self._outlier_count = 0
        self._pause_until = 0.0                # while t_now < pause_until, suppress pose
        self._pose_smooth_pos = None           # LP-smoothed XYZ for single-marker publishes
        self._pose_smooth_q = None             # LP-smoothed quaternion for single-marker publishes
        # Single-marker pre-yaw-lock streak buffer (z-jump self-lock incident
        # 2026-05-26): require 3 consistent single-marker frames before
        # publishing if yaw is not yet locked, so an IPPE-flipped first frame
        # cannot seed downstream filters.
        self._single_streak_pos = collections.deque(maxlen=3)
        self._single_streak_t   = collections.deque(maxlen=3)

        # TF broadcaster + listener (for static base_link → camera transform)
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.tf_broadcaster = TransformBroadcaster(self)
        self.T_cam_to_base = None  # cached 4x4 transform main_camera_optical → base_link

        # Subscribers
        self._img_qos = img_qos
        # camera_info is low-rate; always subscribe.
        self.create_subscription(CameraInfo, 'camera_info', self._camera_info_cb, img_qos)
        if not self.gate_by_flight_state:
            # No gating: images subscribed immediately, full rate always.
            self._image_sub = self.create_subscription(
                Image, 'image_raw', self._image_cb, img_qos)

        if self.use_map_markers:
            from rclpy.qos import QoSDurabilityPolicy
            map_qos = QoSProfile(
                reliability=QoSReliabilityPolicy.RELIABLE,
                history=QoSHistoryPolicy.KEEP_LAST,
                depth=1,
                durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            )
            self.create_subscription(ArucoMarkerArray, 'map_markers', self._map_cb, map_qos)

        # FCU state, for the flight-state detection gate. /mavros/state is
        # RELIABLE + TRANSIENT_LOCAL, so late subscribers still get the latest.
        # A 5 Hz timer applies the gate (create/destroy the image subscription)
        # from a timer callback rather than from _state_cb, to avoid mutating
        # subscriptions re-entrantly from another callback.
        if self.gate_by_flight_state:
            from rclpy.qos import QoSDurabilityPolicy
            state_qos = QoSProfile(
                reliability=QoSReliabilityPolicy.RELIABLE,
                history=QoSHistoryPolicy.KEEP_LAST,
                depth=1,
                durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            )
            self.create_subscription(State, '/mavros/state', self._state_cb, state_qos)
            self.create_timer(0.2, self._apply_detection_gate)

        self.get_logger().info(
            f'aruco_detect ready (dict={dict_id}, length={self.default_length}, '
            f'estimate_poses={self.estimate_poses}, use_map={self.use_map_markers}, '
            f'gate_by_flight_state={self.gate_by_flight_state})')

    def _state_cb(self, msg):
        self._fcu_mode = str(msg.mode)
        self._fcu_armed = bool(msg.armed)

    def _detect_full_rate(self):
        """True when detection is warranted (autonomous mission armed/OFFBOARD)."""
        if not self.gate_by_flight_state:
            return True
        if self._fcu_mode == 'OFFBOARD':
            return True
        if self.full_rate_when_armed and self._fcu_armed:
            return True
        return False

    def _apply_detection_gate(self):
        """Create/destroy the image_raw subscription to match flight state.

        Destroying the subscription when idle stops the 24 Hz camera stream from
        being delivered at all -- the only way to actually drop CPU, since a
        per-frame skip still pays the deserialization cost of every frame.
        """
        want = self._detect_full_rate()
        if want and self._image_sub is None:
            self._image_sub = self.create_subscription(
                Image, 'image_raw', self._image_cb, self._img_qos)
            self.get_logger().info(
                'aruco: detection ACTIVE (armed=%s mode=%s)'
                % (self._fcu_armed, self._fcu_mode))
        elif not want and self._image_sub is not None:
            self.destroy_subscription(self._image_sub)
            self._image_sub = None
            self.get_logger().info('aruco: detection IDLE (disarmed) -- camera stream released')

    def _camera_info_cb(self, msg):
        if msg.k[0] == 0.0:
            return
        self.camera_matrix = np.array(msg.k, dtype=np.float64).reshape(3, 3)
        self.dist_coeffs = np.array(msg.d, dtype=np.float64)
        _model = (msg.distortion_model or '').lower()
        self.fisheye = (_model in ('equidistant', 'fisheye', 'kannala_brandt')
                        or self.dist_coeffs.size == 4)
        # Try to build the undistort map as soon as we know W/H (CameraInfo
        # carries width/height — image_cb does not need to fire first).
        W = int(msg.width)
        H = int(msg.height)
        if W > 0 and H > 0:
            self._build_undistort_maps(W, H)

    def _build_undistort_maps(self, W, H):
        """Pre-compute remap LUTs so each frame is rectified before
        detectMarkers, and every PnP call can use zero distortion."""
        if self.camera_matrix is None:
            return
        if self._undistort_size == (W, H) and self._undistort_map1 is not None:
            return  # already built for this resolution
        try:
            if self.fisheye:
                Df = np.asarray(self.dist_coeffs, dtype=np.float64).reshape(4, 1)
                # estimateNewCameraMatrixForUndistortRectify collapses to a
                # degenerate K (fx=0) on strong fisheye D -> reuse K directly as
                # the pinhole target (centre maps 1:1, PnP uses K + zero dist).
                new_K = self.camera_matrix.copy()
                map1, map2 = cv2.fisheye.initUndistortRectifyMap(
                    self.camera_matrix, Df, np.eye(3), new_K, (W, H), cv2.CV_16SC2)
            else:
                D = self.dist_coeffs if self.dist_coeffs is not None else np.zeros(5)
                new_K, _ = cv2.getOptimalNewCameraMatrix(
                    self.camera_matrix, D, (W, H), 0.0, (W, H))
                map1, map2 = cv2.initUndistortRectifyMap(
                    self.camera_matrix, D, None, new_K, (W, H), cv2.CV_16SC2)
        except cv2.error as e:
            self.get_logger().warn(
                f'undistort map build failed ({W}x{H}): {e}; '
                'falling back to distorted pipeline',
                throttle_duration_sec=10.0)
            return
        self._undistort_map1 = map1
        self._undistort_map2 = map2
        self._K_undist = new_K
        self._undistort_size = (W, H)
        if not self._undistort_logged:
            fx_n = float(new_K[0, 0]); fy_n = float(new_K[1, 1])
            cx_n = float(new_K[0, 2]); cy_n = float(new_K[1, 2])
            self.get_logger().info(
                'aruco_detect undistort active [%s]: using new_K=[[%.2f, 0, %.2f], '
                '[0, %.2f, %.2f], [0, 0, 1]] (%dx%d), distCoeffs=zeros for '
                'PnP after frame undistort'
                % ('FISHEYE' if self.fisheye else 'plumb_bob',
                   fx_n, cx_n, fy_n, cy_n, W, H))
            self._undistort_logged = True

    def _map_cb(self, msg):
        self.map_markers = {}
        for m in msg.markers:
            # Build 4x4 transform from marker pose in map frame
            p = m.pose.position
            q = m.pose.orientation
            R = quaternion_to_rotation_matrix(q.x, q.y, q.z, q.w)
            T = np.eye(4)
            T[:3, :3] = R
            T[:3, 3] = [p.x, p.y, p.z]
            self.map_markers[m.id] = {'length': m.length, 'T': T}
        self.get_logger().info(f'Received map with {len(self.map_markers)} markers: {list(self.map_markers.keys())}')
        self._rebuild_board()

    def _rebuild_board(self):
        """Build cv2.aruco.Board from current map_markers for refineDetectedMarkers."""
        if not self.refine_with_board or not self.map_markers:
            self.aruco_board = None
            return
        obj_points_list = []
        ids_list = []
        for mid, mdata in self.map_markers.items():
            L = float(mdata['length'])
            T = mdata['T']
            # Marker corner order (matches detectMarkers): TL, TR, BR, BL on z=0 plane in marker frame
            local = np.array([
                [-L / 2,  L / 2, 0.0, 1.0],
                [ L / 2,  L / 2, 0.0, 1.0],
                [ L / 2, -L / 2, 0.0, 1.0],
                [-L / 2, -L / 2, 0.0, 1.0],
            ], dtype=np.float64)
            world = (T @ local.T).T[:, :3].astype(np.float32)
            obj_points_list.append(world)
            ids_list.append(int(mid))
        try:
            ids_arr = np.array(ids_list, dtype=np.int32)
            # OpenCV >=4.7 Board constructor takes (objPoints, dictionary, ids)
            self.aruco_board = cv2.aruco.Board(obj_points_list, self.aruco_dict, ids_arr)
            self.get_logger().info(f'Built ArUco board for refinement: {len(ids_list)} markers')
        except Exception as e:
            self.aruco_board = None
            self.get_logger().warn(f'Could not build ArUco board: {e}')

    def _load_map_file(self, path):
        """Load map markers from map.txt file.

        Format: id  length  x  y  z  rot_z  rot_y  rot_x
        Rotations are Euler angles in radians (ZYX convention).
        """
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split()
                    if len(parts) < 8:
                        continue
                    mid = int(parts[0])
                    length = float(parts[1])
                    x, y, z = float(parts[2]), float(parts[3]), float(parts[4])
                    rz, ry, rx = float(parts[5]), float(parts[6]), float(parts[7])

                    # Build rotation matrix from Euler ZYX
                    Rz = np.array([
                        [np.cos(rz), -np.sin(rz), 0],
                        [np.sin(rz), np.cos(rz), 0],
                        [0, 0, 1],
                    ])
                    Ry = np.array([
                        [np.cos(ry), 0, np.sin(ry)],
                        [0, 1, 0],
                        [-np.sin(ry), 0, np.cos(ry)],
                    ])
                    Rx = np.array([
                        [1, 0, 0],
                        [0, np.cos(rx), -np.sin(rx)],
                        [0, np.sin(rx), np.cos(rx)],
                    ])
                    R = Rz @ Ry @ Rx

                    T = np.eye(4)
                    T[:3, :3] = R
                    T[:3, 3] = [x, y, z]
                    self.map_markers[mid] = {'length': length, 'T': T}

            self.get_logger().info(f'Loaded map from {path}: {len(self.map_markers)} markers {list(self.map_markers.keys())}')
            self._rebuild_board()
        except Exception as e:
            self.get_logger().error(f'Failed to load map file {path}: {e}')

    def _lookup_cam_to_base(self, camera_frame):
        """Cache T^{cam}_{base}: the 4x4 matrix that maps base_link points into camera frame.

        lookup_transform(target, source) returns T: p_target = T * p_source
        So lookup(camera_frame, 'base_link') gives T^{cam}_{base}.
        Composition: T^{map}_{base} = T^{map}_{cam} @ T^{cam}_{base}
        """
        if self.T_cam_to_base is not None:
            return self.T_cam_to_base
        try:
            import rclpy.time
            from rclpy.duration import Duration
            tf = self.tf_buffer.lookup_transform(
                camera_frame, 'base_link',
                rclpy.time.Time(), Duration(seconds=0.1))
            t = tf.transform.translation
            q = tf.transform.rotation
            R = quaternion_to_rotation_matrix(q.x, q.y, q.z, q.w)
            T = np.eye(4)
            T[:3, :3] = R
            T[:3, 3] = [t.x, t.y, t.z]
            self.T_cam_to_base = T
            self.get_logger().info(f'Cached static TF base_link in {camera_frame}')
            return self.T_cam_to_base
        except Exception as e:
            self.get_logger().debug(f'Waiting for static TF: {e}')
            return None

    def _compute_map_pose(self, rvec, tvec, marker_id, camera_frame):
        """Compute base_link pose in map frame from ONE detected map marker.

        T^{map}_{base} = T^{map}_{cam} @ T^{cam}_{base}
        where T^{map}_{cam} = T^{map}_{marker} @ inv(T^{cam}_{marker})

        Returns (pos:ndarray(3), quat:ndarray(4)) or None.
        """
        if marker_id not in self.map_markers:
            return None

        R_mc, _ = cv2.Rodrigues(rvec)
        T_cam_marker_inv = np.eye(4)
        T_cam_marker_inv[:3, :3] = R_mc.T
        T_cam_marker_inv[:3, 3] = -R_mc.T @ tvec.flatten()
        T_map_marker = self.map_markers[marker_id]['T']
        T_map_cam = T_map_marker @ T_cam_marker_inv

        T_cam_base = self._lookup_cam_to_base(camera_frame)
        if T_cam_base is not None:
            T_map_base = T_map_cam @ T_cam_base
        else:
            T_map_base = T_map_cam

        pos = T_map_base[:3, 3].copy()
        qx, qy, qz, qw = rotation_matrix_to_quaternion(T_map_base[:3, :3])
        return pos, np.array([qx, qy, qz, qw], dtype=np.float64)

    def _solve_ippe_candidates(self, marker_length, c, marker_id):
        """All IPPE_SQUARE candidates for one marker (each candidate may be the
        mirror flip of the other). Returns list of (rvec, tvec, reproj_err)."""
        if self.camera_matrix is None:
            return []
        m = float(marker_length) * 0.5
        obj_points = np.array([
            [-m,  m, 0.0],
            [ m,  m, 0.0],
            [ m, -m, 0.0],
            [-m, -m, 0.0],
        ], dtype=np.float64)
        # Block D: when remap is active the frame is already rectified, so PnP
        # must use the rectified K with zero distortion. Otherwise OpenCV would
        # compensate for D twice and bias z under tilt.
        if self._undistort_map1 is not None and self._K_undist is not None:
            K_pnp = self._K_undist
            D_pnp = self._D_zero
        else:
            K_pnp = self.camera_matrix
            D_pnp = self.dist_coeffs if self.dist_coeffs is not None else np.zeros(5)
        try:
            ok, rvecs, tvecs, errs = cv2.solvePnPGeneric(
                obj_points,
                c.astype(np.float64),
                K_pnp,
                D_pnp,
                flags=cv2.SOLVEPNP_IPPE_SQUARE)
        except cv2.error:
            return []
        if not ok or len(rvecs) == 0:
            return []
        try:
            errs_arr = np.array(errs, dtype=np.float64).flatten()
        except Exception:
            errs_arr = np.zeros(len(rvecs))
        return [
            (rvecs[i], tvecs[i],
             float(errs_arr[i]) if i < len(errs_arr) else 0.0)
            for i in range(len(rvecs))
        ]

    def _pick_candidate(self, candidates, marker_id):
        """Default IPPE candidate selection: warm-start tvec if known, otherwise
        marker-normal-faces-camera test, else lowest reprojection error."""
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        errs = [float(c[2]) for c in candidates]
        if min(errs) > 1e-9 and max(errs) > _IPPE_AMBIG_RATIO * min(errs):
            return candidates[int(np.argmin(errs))]
        prev = self._last_marker_tvec.get(marker_id)
        if prev is not None:
            dists = [
                float(np.linalg.norm(np.asarray(c[1]).flatten() - prev))
                for c in candidates
            ]
            return candidates[int(np.argmin(dists))]
        scores = []
        for rvec, tvec, _ in candidates:
            R, _ = cv2.Rodrigues(np.asarray(rvec))
            n = R[:, 2]
            t = np.asarray(tvec).flatten()
            tn = np.linalg.norm(t)
            scores.append(float(np.dot(n, -t / tn)) if tn > 1e-6 else -1.0)
        best = int(np.argmax(scores))
        if scores[best] <= 0.0:
            errs = [c[2] for c in candidates]
            best = int(np.argmin(errs)) if errs else 0
        return candidates[best]

    def _disambig_candidate(self, candidates, marker_id, camera_frame):
        """Pick IPPE candidate using yaw_world if locked, else fall back to
        warm-start logic. Returns the candidate (rvec, tvec, err)."""
        if not candidates:
            return None
        if (self._yaw_world is None or len(candidates) == 1
                or marker_id not in self.map_markers):
            return self._pick_candidate(candidates, marker_id)
        errs = [float(c[2]) for c in candidates]
        if min(errs) > 1e-9 and max(errs) > _IPPE_AMBIG_RATIO * min(errs):
            return candidates[int(np.argmin(errs))]
        best = None
        best_dy = float('inf')
        for cand in candidates:
            res = self._compute_map_pose(cand[0], cand[1], marker_id, camera_frame)
            if res is None:
                continue
            yaw_obs = yaw_from_quat(res[1])
            dy = abs(wrap_pi(yaw_obs - self._yaw_world))
            if dy < best_dy:
                best_dy = dy
                best = cand
        if best is None or best_dy > _YAW_DISAMBIG_TOL_RAD:
            return self._pick_candidate(candidates, marker_id)
        return best

    def _normalized_center_dist(self, c, w, h):
        """Marker-corner-mean distance from image centre, normalised so that
        a corner-of-frame marker is ~0.71 and a centred marker is 0."""
        cx = float(c[:, 0].mean())
        cy = float(c[:, 1].mean())
        dx = (cx - w * 0.5) / (w * 0.5)
        dy = (cy - h * 0.5) / (h * 0.5)
        return math.hypot(dx, dy) / math.sqrt(2.0)

    def _publish_quality_signals(self, markers_used):
        """Tell vpe_fix how many markers we used and whether yaw is locked."""
        m_msg = Int32()
        m_msg.data = int(markers_used)
        self.markers_used_pub.publish(m_msg)
        l_msg = Bool()
        l_msg.data = bool(self._yaw_world_locked)
        self.yaw_locked_pub.publish(l_msg)

    def _update_yaw_lock(self, yaw_obs, markers_used, t_now):
        """Promote yaw_world to "locked" via two paths:

        Multi-marker (fast): ≥1.5s of continuous ≥2-marker visibility — the
        cross-marker baseline kills IPPE mirror flip geometrically, so we trust
        any consistent yaw reading.

        Single-marker (slow): ≥3.0s of continuous single-marker pose updates AND
        rolling yaw spread under 8°. The spread test rejects the case where IPPE
        oscillates between the two flip candidates (which would cause a high
        spread). Once locked, single-marker frames are accepted by vpe_fix.

        Lock is dropped only by long vision silence (handled in _image_cb), not
        by a transient single-marker dip after a multi-marker observation.
        """
        if markers_used >= _QUORUM_MIN_MARKERS:
            if self._yaw_world is None:
                self._yaw_world = yaw_obs
            else:
                d = wrap_pi(yaw_obs - self._yaw_world)
                self._yaw_world = wrap_pi(
                    self._yaw_world + _YAW_LP_ALPHA * d)
            # Reset single-marker accumulators when multi-marker re-engages.
            if self._yaw_lock_via_single and not self._yaw_world_locked:
                self._yaw_world_lock_start = t_now
                self._yaw_lock_via_single = False
                self._yaw_single_samples = []
            elif self._yaw_world_lock_start is None:
                self._yaw_world_lock_start = t_now
                self._yaw_lock_via_single = False
            elif (not self._yaw_world_locked
                    and (t_now - self._yaw_world_lock_start)
                    >= _YAW_LOCK_WINDOW_S):
                self._yaw_world_locked = True
                self.get_logger().info(
                    'aruco_detect: yaw_world locked at %.1f deg (multi-marker)'
                    % math.degrees(self._yaw_world))
            return

        if markers_used == 1:
            # Single-marker path. Seed yaw_world from the first sample, then
            # accept observations within ±30° of it.
            if self._yaw_world is None:
                self._yaw_world = yaw_obs
                self._yaw_world_lock_start = t_now
                self._yaw_lock_via_single = True
                self._yaw_single_samples = [yaw_obs]
                return

            d = wrap_pi(yaw_obs - self._yaw_world)
            if abs(d) > _YAW_LOCK_SINGLE_MAX_DEV and not self._yaw_world_locked:
                # Probably the mirror flip — re-seed instead of contaminating LP.
                self._yaw_world = yaw_obs
                self._yaw_world_lock_start = t_now
                self._yaw_lock_via_single = True
                self._yaw_single_samples = [yaw_obs]
                return

            self._yaw_world = wrap_pi(
                self._yaw_world + _YAW_LP_ALPHA * d)
            self._yaw_single_samples.append(yaw_obs)
            if len(self._yaw_single_samples) > 30:
                self._yaw_single_samples.pop(0)

            if (not self._yaw_world_locked
                    and self._yaw_world_lock_start is not None
                    and (t_now - self._yaw_world_lock_start)
                    >= _YAW_LOCK_SINGLE_WINDOW_S
                    and len(self._yaw_single_samples) >= _YAW_LOCK_SINGLE_SAMPLES
                    and self._yaw_spread(self._yaw_single_samples)
                    < _YAW_LOCK_SINGLE_SPREAD_RAD):
                self._yaw_world_locked = True
                self._yaw_lock_via_single = True
                self.get_logger().info(
                    'aruco_detect: yaw_world locked at %.1f deg (single-marker, spread=%.1f deg)'
                    % (math.degrees(self._yaw_world),
                       math.degrees(self._yaw_spread(self._yaw_single_samples))))
            return

        # No markers at all — only reset the window if we never locked.
        if not self._yaw_world_locked:
            self._yaw_world_lock_start = None

    @staticmethod
    def _yaw_spread(yaws):
        """Min-to-max yaw spread (rad), wrap-aware around the first sample."""
        if not yaws:
            return 0.0
        base = yaws[0]
        rel = [wrap_pi(y - base) for y in yaws]
        return max(rel) - min(rel)

    def _check_velocity_gate(self, pos, t_now, n_markers):
        """Reject pose if implied speed exceeds the per-marker-count limit.

        Multi-marker poses are geometrically constrained; a 2.5 m/s gate is
        enough. Single-marker poses are sensitive to pitch/roll-induced
        perspective coupling — a slow takeoff still produces vision-only Z
        jumps over 1 m, so we tighten the limit to 1.5 m/s. Three consecutive
        outliers force a quiet window.
        """
        if t_now < self._pause_until:
            return False
        limit = _VEL_LIMIT_SINGLE_MPS if n_markers <= 1 else _VEL_LIMIT_MPS
        if self._last_pub_t is not None and self._last_pub_pos is not None:
            dt = t_now - self._last_pub_t
            if 0.0 < dt <= 1.0:
                v = float(np.linalg.norm(np.asarray(pos) - self._last_pub_pos)) / dt
                if v > limit:
                    self._outlier_count += 1
                    if self._outlier_count >= 3:
                        self._pause_until = t_now + _OUTLIER_PAUSE_S
                        self._outlier_count = 0
                        self._last_pub_pos = None
                        self._last_pub_t = None
                    return False
        self._outlier_count = 0
        return True

    def _publish_fused_map_pose(self, candidates, header, markers_used, single_marker_ok):
        """Publish a single fused map pose with adaptive covariance.

        candidates: list of (pos:ndarray(3), quat:ndarray(4)) — one per visible map marker.
        markers_used: how many of those candidates survived our gates (informational).
        single_marker_ok: only relevant when len(candidates)==1; if False we drop the frame
                          entirely (single-marker geometry too poor to trust).
        Returns fused position (ndarray(3)) or None.
        """
        if not candidates:
            return None
        if len(candidates) == 1 and not single_marker_ok:
            return None

        positions = np.array([c[0] for c in candidates])
        quaternions = np.array([c[1] for c in candidates])

        if len(candidates) >= 2:
            median = np.median(positions, axis=0)
            mask = np.linalg.norm(positions - median, axis=1) <= 0.5
            if not np.any(mask):
                return None
            positions = positions[mask]
            quaternions = quaternions[mask]

        pos_avg = np.mean(positions, axis=0)
        q0 = quaternions[0]
        q_sum = np.zeros(4, dtype=np.float64)
        for q in quaternions:
            q_sum += q if np.dot(q, q0) >= 0 else -q
        q_norm = q_sum / np.linalg.norm(q_sum)

        # Number of markers actually used (after outlier reject).
        n_used = int(positions.shape[0])

        # Velocity outlier gate (tighter for single-marker, where pitch/roll-induced
        # perspective coupling produces large fake jumps).
        t_now = self.get_clock().now().nanoseconds * 1e-9
        if not self._check_velocity_gate(pos_avg, t_now, n_used):
            return None

        # Per-count covariance. Single-marker is intentionally LOOSE on Z so
        # baro dominates altitude (PnP Z from a small marker is the most
        # pitch-sensitive axis). XY/yaw stay informative but not over-tight.
        # Multi-marker tightens to give EKF strong vision lock.
        cov = [0.0] * 36
        if n_used <= 1:
            cov[0]  = 0.30 ** 2     # XY sigma 0.30 m
            cov[7]  = 0.30 ** 2
            cov[14] = 2.00 ** 2     # 2026-06-05: REVERTED back to original. The 0.80 tighten gave catastrophic overshoot in flight_marker test: EKF trusted noisy single-marker IPPE Z, jumped to 1.82m, MPC dove to -0.24m. Vision Z too noisy at altitude due to 5x camera_fix interp -- baro must dominate Z.
            cov[35] = 0.10 ** 2     # yaw sigma 5.7°
        elif n_used == 2:
            # 2026-06-17 Block F: σz softened (0.20→0.50) — 2-marker Z still
            # noisier than 3+, but XY/yaw kept informative.
            cov[0]  = 0.10 ** 2
            cov[7]  = 0.10 ** 2
            cov[14] = 0.50 ** 2
            cov[35] = 0.05 ** 2
        else:                       # ≥3 markers — tightest
            # 2026-06-17 Block F: tighter XY (0.10→0.05) and Z (0.15→0.10)
            # to give EKF strongest vision lock when geometry is overdetermined.
            cov[0]  = 0.05 ** 2
            cov[7]  = 0.05 ** 2
            cov[14] = 0.10 ** 2
            cov[35] = 0.05 ** 2
        cov[21] = 1e6
        cov[28] = 1e6

        # Hybrid output: smooth single-marker frames (kills high-frequency PnP
        # corner jitter that the controller would otherwise chase as real motion),
        # publish multi-marker frames raw (full responsiveness — no extra latency
        # for flight scripts that work between marker columns). The smoothing
        # buffer is seeded from any successful publish so the next single-marker
        # frame doesn't snap back to a stale value.
        if n_used <= 1 and self._pose_smooth_pos is not None:
            a = _SINGLE_MARKER_LP_ALPHA
            self._pose_smooth_pos = a * pos_avg + (1.0 - a) * self._pose_smooth_pos
            q_blend = q_norm if np.dot(q_norm, self._pose_smooth_q) >= 0 else -q_norm
            self._pose_smooth_q = a * q_blend + (1.0 - a) * self._pose_smooth_q
            qn = float(np.linalg.norm(self._pose_smooth_q))
            if qn > 1e-9:
                self._pose_smooth_q = self._pose_smooth_q / qn
            pos_pub = self._pose_smooth_pos
            q_pub = self._pose_smooth_q
        else:
            # Multi-marker (or first single-marker frame after silence): publish raw,
            # and seed the smoothing buffer with the trusted multi-marker pose.
            self._pose_smooth_pos = pos_avg.copy()
            self._pose_smooth_q = q_norm.copy()
            pos_pub = pos_avg
            q_pub = q_norm

        # Pre-yaw-lock single-marker gate (z-jump self-lock incident 2026-05-26):
        # before yaw is locked, single-marker PnP is vulnerable to IPPE mirror
        # flip. Require 3 consistent single-marker frames before publishing.
        # _update_yaw_lock must still run on raw observations regardless of
        # publish — so we run it explicitly before returning when gated out.
        suppress_publish = False
        if n_used == 1:
            if not self._yaw_world_locked:
                self._single_streak_pos.append(np.array([pos_avg[0], pos_avg[1], pos_avg[2]]))
                self._single_streak_t.append(t_now)
                if len(self._single_streak_pos) < 3:
                    suppress_publish = True
                elif (self._single_streak_t[-1] - self._single_streak_t[0]) > 1.5:
                    # Gap too large -- restart streak.
                    self._single_streak_pos.clear()
                    self._single_streak_t.clear()
                    self._single_streak_pos.append(np.array([pos_avg[0], pos_avg[1], pos_avg[2]]))
                    self._single_streak_t.append(t_now)
                    suppress_publish = True
                else:
                    arr = np.vstack(self._single_streak_pos)
                    if float(arr.std(axis=0).max()) > 0.10:
                        # Disagreement (likely IPPE flip) -- drop streak, restart.
                        self._single_streak_pos.clear()
                        self._single_streak_t.clear()
                        suppress_publish = True
            else:
                # Yaw locked -- single-marker is trustworthy; clear streak.
                self._single_streak_pos.clear()
                self._single_streak_t.clear()

        if suppress_publish:
            # Still update yaw lock + velocity-gate history on raw observation.
            yaw_obs = yaw_from_quat(np.array(q_norm, dtype=np.float64))
            self._update_yaw_lock(yaw_obs, n_used, t_now)
            self._last_pub_pos = pos_avg.copy()
            self._last_pub_t = t_now
            return None

        pose_msg = PoseWithCovarianceStamped()
        pose_msg.header.stamp = header.stamp
        pose_msg.header.frame_id = self.map_frame_id
        pose_msg.pose.pose.position = Point(x=float(pos_pub[0]), y=float(pos_pub[1]), z=float(pos_pub[2]))
        pose_msg.pose.pose.orientation = Quaternion(
            x=float(q_pub[0]), y=float(q_pub[1]), z=float(q_pub[2]), w=float(q_pub[3]))
        pose_msg.pose.covariance = cov
        self.map_pose_pub.publish(pose_msg)

        t = TransformStamped()
        t.header.stamp = header.stamp
        t.header.frame_id = self.map_frame_id
        t.child_frame_id = 'base_link'
        t.transform.translation.x = float(pos_pub[0])
        t.transform.translation.y = float(pos_pub[1])
        t.transform.translation.z = float(pos_pub[2])
        t.transform.rotation = Quaternion(
            x=float(q_pub[0]), y=float(q_pub[1]), z=float(q_pub[2]), w=float(q_pub[3]))
        self.tf_broadcaster.sendTransform(t)

        # Yaw-lock builds on the smoothed yaw (more stable signal). Velocity
        # gate next frame compares against RAW pose so smoothing doesn't hide
        # real outliers — that's why _last_pub_pos stores pos_avg, not pos_pub.
        yaw_obs = yaw_from_quat(np.array(q_pub, dtype=np.float64))
        self._update_yaw_lock(yaw_obs, n_used, t_now)
        self._last_pub_pos = pos_avg.copy()
        self._last_pub_t = t_now

        return pos_pub

    def _publish_map_image(self, header, detected_ids, cam_pos=None):
        """Publish a top-down map visualization.

        The view auto-fits to the marker bounds (with a margin) so a dense
        grid spreads into individually readable squares instead of merging
        into bars at a fixed wide scale.
        """
        if self.map_image_pub.get_subscription_count() == 0:
            return
        if not self.map_markers:
            return

        W, H = 280, 280
        margin = 34  # px border so edge squares + labels are not clipped
        img = np.zeros((H, W, 3), dtype=np.uint8)

        xs = [m['T'][0, 3] for m in self.map_markers.values()]
        ys = [m['T'][1, 3] for m in self.map_markers.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span_x = max(max_x - min_x, 0.5)
        span_y = max(max_y - min_y, 0.5)
        scale = min((W - 2 * margin) / span_x, (H - 2 * margin) / span_y)
        wcx = 0.5 * (min_x + max_x)
        wcy = 0.5 * (min_y + max_y)

        def to_px(wx, wy):
            return (int(round(W * 0.5 + (wx - wcx) * scale)),
                    int(round(H * 0.5 - (wy - wcy) * scale)))

        # Marker squares + id labels (label to the right of each square).
        for mid, mdata in self.map_markers.items():
            mx, my = to_px(mdata['T'][0, 3], mdata['T'][1, 3])
            color = (0, 230, 0) if mid in detected_ids else (110, 110, 110)
            cv2.rectangle(img, (mx - 4, my - 4), (mx + 4, my + 4), color, -1)
            cv2.putText(img, str(mid), (mx + 6, my + 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1, cv2.LINE_AA)

        # Camera position: red dot, clamped into frame. Its label is offset to
        # the LEFT so it never overlaps a marker id (drawn to the right).
        if cam_pos is not None:
            px, py = to_px(cam_pos[0], cam_pos[1])
            px = min(max(px, 4), W - 5)
            py = min(max(py, 4), H - 5)
            cv2.circle(img, (px, py), 4, (0, 0, 255), -1)
            lx = min(max(px - 36, 2), W - 42)
            ly = min(max(py - 8, 12), H - 4)
            cv2.putText(img, 'CAM', (lx, ly),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 0, 255), 1, cv2.LINE_AA)

        msg = Image()
        msg.header = header
        msg.height = H
        msg.width = W
        msg.encoding = 'bgr8'
        msg.step = W * 3
        msg.data = img.tobytes()
        self.map_image_pub.publish(msg)

    def _image_cb(self, msg):
        if not self.enabled:
            return

        # Convert ROS Image to OpenCV
        if msg.encoding == 'rgb8':
            img = np.frombuffer(bytes(msg.data), dtype=np.uint8).reshape(msg.height, msg.width, 3)
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        elif msg.encoding == 'bgr8':
            img = np.frombuffer(bytes(msg.data), dtype=np.uint8).reshape(msg.height, msg.width, 3)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            bgr = img
        elif msg.encoding == 'mono8':
            gray = np.frombuffer(bytes(msg.data), dtype=np.uint8).reshape(msg.height, msg.width)
            bgr = None  # built after undistort so the debug overlay matches gray
        else:
            self.get_logger().warn(f'Unsupported encoding: {msg.encoding}', throttle_duration_sec=5)
            return

        # ── Frame undistortion (Block D) ──
        # Run BEFORE gamma/CLAHE/unsharp so all preprocessing operates on the
        # rectified image and downstream PnP uses self._K_undist with D=0.
        # Lazy-build the map the first time we have both K and a frame size.
        if self._undistort_map1 is None and self.camera_matrix is not None:
            self._build_undistort_maps(int(msg.width), int(msg.height))
        if self._undistort_map1 is not None:
            gray = cv2.remap(
                gray, self._undistort_map1, self._undistort_map2,
                interpolation=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT, borderValue=0)
            # alpha=0 already removes black borders, but the few-pixel ring
            # near the rectified edge can still light up adaptive_threshold.
            # Zero a 4-px frame so detectMarkers never sees a synthetic edge.
            gray[:4, :] = 0
            gray[-4:, :] = 0
            gray[:, :4] = 0
            gray[:, -4:] = 0

        # bgr is used only for the debug overlay; (re)build it from the (now
        # possibly undistorted) gray so drawn markers align with the rectified
        # image. For colour input encodings we keep the original bgr — it would
        # need its own remap to match, which is not worth the cost for the
        # debug topic (overlay corners still come from gray-space detect).
        if bgr is None:
            bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

        # ── Block B: adaptive preprocessing by luma statistics ──
        # Stats are computed on the post-undistort, pre-LUT frame so the
        # classifier sees the same intensity distribution detectMarkers will
        # later operate on. Hysteresis: don't switch modes faster than 0.5 s.
        mu = float(gray.mean())
        p_lo, p_hi = np.percentile(gray, [5, 95])
        sat_hi = float((gray > 245).mean())
        if sat_hi > 0.05:
            target_mode = 'BACKLIGHT'
        elif mu < 60:
            target_mode = 'LOW_LIGHT'
        elif (p_hi - p_lo) < 60:
            target_mode = 'LOW_CONTRAST'
        else:
            target_mode = 'NORMAL'
        t_now_pre = self.get_clock().now().nanoseconds * 1e-9
        if (target_mode != self._preproc_mode
                and (t_now_pre - self._preproc_mode_since) >= 0.5):
            self.get_logger().info(
                'preproc mode=%s mu=%.0f sat_hi=%.2f p_hi-p_lo=%.0f'
                % (target_mode, mu, sat_hi, float(p_hi - p_lo)))
            self._preproc_mode = target_mode
            self._preproc_mode_since = t_now_pre
        preset = self._preproc[self._preproc_mode]

        # Gamma LUT — lifts shadows (or pulls highlights) before CLAHE
        gray = cv2.LUT(gray, preset['lut'])

        # Keep the gamma-only frame for the optional no-CLAHE retry pass.
        gray_pre_clahe = (gray if self.retry_no_clahe else None)

        # CLAHE — local contrast normalization for shadow / uneven lighting
        gray = preset['clahe'].apply(gray)

        # Unsharp mask — edge boost for motion blur and oblique angles
        if self.use_unsharp:
            blurred = cv2.GaussianBlur(gray, (0, 0), self.unsharp_sigma)
            ua = float(preset['unsharp_amount'])
            gray = cv2.addWeighted(gray, 1.0 + ua,
                                   blurred, -ua, 0)

        self.frame_idx += 1
        H_img, W_img = gray.shape

        # Multi-pass detection. Priority: 0=full-frame (best corners), 1=ROI, 2=downscale.
        # Later passes only overwrite earlier ones if higher priority (lower number).
        detections = {}  # marker_id -> (corners_array shape (1,4,2), priority)

        # ── Pass 1: ROI-tracked detection on previous-frame marker bboxes ──
        for (rx, ry, rw, rh) in self.prev_marker_rois:
            x0 = max(0, rx); y0 = max(0, ry)
            x1 = min(W_img, rx + rw); y1 = min(H_img, ry + rh)
            if x1 - x0 < self.track_roi_min_px or y1 - y0 < self.track_roi_min_px:
                continue
            roi = gray[y0:y1, x0:x1]
            r_corners, r_ids, _ = self.detector_track.detectMarkers(roi)
            if r_ids is not None:
                for rc, rid in zip(r_corners, r_ids.flatten()):
                    tc = rc.copy()
                    tc[0, :, 0] += x0
                    tc[0, :, 1] += y0
                    detections[int(rid)] = (tc, 1)

        # ── Pass 2: Full-frame detection (highest priority, overrides ROI) ──
        corners, ids, rejected = self.detector.detectMarkers(gray)
        if ids is not None:
            for fc, fid in zip(corners, ids.flatten()):
                detections[int(fid)] = (fc, 0)

        # ── Pass 3: Downscale detection (every Nth frame, recovers small markers) ──
        # With native Aruco3 enabled this is largely redundant — the detector
        # already searches a pyramid internally — but it's cheap insurance and
        # also catches markers that fall just under minSideLengthCanonicalImg on
        # the full-resolution pass.
        if (self.aruco3_downscale_every_n > 0
                and self.frame_idx % self.aruco3_downscale_every_n == 0
                and W_img >= 320 and H_img >= 240):
            sw, sh = W_img // 2, H_img // 2
            small = cv2.resize(gray, (sw, sh), interpolation=cv2.INTER_AREA)
            s_corners, s_ids, _ = self.detector.detectMarkers(small)
            if s_ids is not None:
                for sc, sid in zip(s_corners, s_ids.flatten()):
                    if int(sid) not in detections:
                        detections[int(sid)] = (sc.astype(np.float32) * 2.0, 2)

        # ── Pass 4 (optional, default off): no-CLAHE retry on empty frames ──
        # CLAHE's tile-local stretch can destroy marker interiors across a hard
        # shadow boundary; the gamma-only image then still decodes. Runs at most
        # every 2nd detection-empty frame to bound CPU.
        if (self.retry_no_clahe and not detections
                and gray_pre_clahe is not None
                and self.frame_idx % 2 == 0):
            n_corners, n_ids, _ = self.detector.detectMarkers(gray_pre_clahe)
            if n_ids is not None:
                for nc, nid in zip(n_corners, n_ids.flatten()):
                    detections[int(nid)] = (nc, 3)

        # ── Block C: lost-tracking recovery via SEARCHING profile ──
        # State machine: after 8 consecutive empty frames go SEARCHING (wider
        # adaptive_threshold sweep + inverted markers + lower Aruco3 size floor
        # + no-CLAHE retry); after 3 successful detections fall back to NORMAL.
        # Profile change pushes the new DetectorParameters into self.detector
        # so the *next* frame uses them; current frame is already done.
        if detections:
            self._search_success_count += 1
            self._search_empty_count = 0
            if (self._search_profile == 'SEARCHING'
                    and self._search_success_count >= 3):
                try:
                    self.detector.setDetectorParameters(self._aruco_params_normal)
                except AttributeError:
                    self.detector = cv2.aruco.ArucoDetector(
                        self.aruco_dict, self._aruco_params_normal,
                        self.refine_params)
                self.retry_no_clahe = self._retry_no_clahe_normal
                self._search_profile = 'NORMAL'
                self.get_logger().info('searching profile -> NORMAL')
        else:
            self._search_empty_count += 1
            self._search_success_count = 0
            if (self._search_profile == 'NORMAL'
                    and self._search_empty_count >= 8):
                try:
                    self.detector.setDetectorParameters(self._aruco_params_searching)
                except AttributeError:
                    self.detector = cv2.aruco.ArucoDetector(
                        self.aruco_dict, self._aruco_params_searching,
                        self.refine_params)
                self.retry_no_clahe = True
                self._search_profile = 'SEARCHING'
                self.get_logger().info(
                    'searching profile -> SEARCHING (8 empty frames)')

        # Rebuild corners/ids from merged detections (sorted for stable order)
        if detections:
            ids_sorted = sorted(detections.keys())
            ids = np.array(ids_sorted, dtype=np.int32).reshape(-1, 1)
            corners = tuple(detections[mid][0] for mid in ids_sorted)
        else:
            ids = None
            corners = ()

        # Refinement: use map geometry to recover map markers that strict detection missed.
        # Requires at least 1 already-detected marker as anchor for board pose, plus
        # rejected candidates to refine. Calling with None ids segfaults the C++ binding.
        if (self.aruco_board is not None and self.camera_matrix is not None
                and ids is not None and len(ids) >= 1
                and rejected is not None and len(rejected) > 0):
            # Block D: refine on the same (K, D) the detector frame matches.
            if self._undistort_map1 is not None and self._K_undist is not None:
                K_refine = self._K_undist
                D_refine = self._D_zero
            else:
                K_refine = self.camera_matrix
                D_refine = self.dist_coeffs
            try:
                corners, ids, rejected, _ = self.detector.refineDetectedMarkers(
                    gray, self.aruco_board, corners, ids, rejected,
                    cameraMatrix=K_refine,
                    distCoeffs=D_refine)
            except cv2.error as e:
                self.get_logger().debug(f'refineDetectedMarkers failed: {e}',
                                        throttle_duration_sec=10.0)

        # Build MarkerArray message
        markers_msg = ArucoMarkerArray()
        markers_msg.header = msg.header
        cam_pos = None
        detected_ids = set()
        map_pose_candidates = []
        # Parallel lists of per-candidate metadata for the single-marker geometry gate
        # (apparent pixel size, IPPE reproj error, image-centre distance, length).
        map_marker_corners = []
        map_marker_lengths = []
        map_marker_errs = []
        # (rvec, tvec, length) for every successfully posed marker — used for
        # axis rendering on the debug image without a second solvePnP call.
        axes_data = []

        if ids is not None and len(ids) > 0:
            from aruco_pose.msg import Point2D
            for i, marker_id in enumerate(ids.flatten()):
                marker = ArucoMarker()
                marker.id = int(marker_id)
                detected_ids.add(int(marker_id))

                # Get marker length from map or use default
                if self.use_map_markers and marker_id in self.map_markers:
                    marker.length = float(self.map_markers[marker_id]['length'])
                else:
                    marker.length = float(self.default_length)

                # Set corner positions
                c = corners[i][0]
                marker.c1 = Point2D(x=float(c[0][0]), y=float(c[0][1]))
                marker.c2 = Point2D(x=float(c[1][0]), y=float(c[1][1]))
                marker.c3 = Point2D(x=float(c[2][0]), y=float(c[2][1]))
                marker.c4 = Point2D(x=float(c[3][0]), y=float(c[3][1]))

                # Estimate pose: IPPE_SQUARE returns up to 2 candidates (mirror flip).
                # Pick the one consistent with our locked yaw_world (if any), else
                # the warm-start tvec, else marker-normal-vs-camera.
                if self.estimate_poses and self.camera_matrix is not None:
                    cand_list = self._solve_ippe_candidates(
                        marker.length, c, int(marker_id))
                    chosen = self._disambig_candidate(
                        cand_list, int(marker_id), msg.header.frame_id)
                    if chosen is not None:
                        rvec, tvec, err_px = chosen
                        self._last_marker_tvec[int(marker_id)] = (
                            np.asarray(tvec).flatten().copy())

                        x, y, z, w = rvec_to_quaternion(rvec)
                        marker.pose = Pose(
                            position=Point(
                                x=float(tvec[0][0]), y=float(tvec[1][0]),
                                z=float(tvec[2][0])),
                            orientation=Quaternion(x=x, y=y, z=z, w=w),
                        )

                        if self.send_tf:
                            tfm = TransformStamped()
                            tfm.header = msg.header
                            tfm.child_frame_id = f'{self.frame_id_prefix}{marker_id}'
                            tfm.transform.translation.x = float(tvec[0][0])
                            tfm.transform.translation.y = float(tvec[1][0])
                            tfm.transform.translation.z = float(tvec[2][0])
                            tfm.transform.rotation = Quaternion(x=x, y=y, z=z, w=w)
                            self.tf_broadcaster.sendTransform(tfm)

                        axes_data.append((rvec, tvec, float(marker.length)))

                        if marker_id in self.map_markers:
                            cand = self._compute_map_pose(
                                rvec, tvec, marker_id, msg.header.frame_id)
                            if cand is not None:
                                map_pose_candidates.append(cand)
                                map_marker_corners.append(c.copy())
                                map_marker_lengths.append(float(marker.length))
                                map_marker_errs.append(float(err_px))

                markers_msg.markers.append(marker)

            # Draw markers on debug image (reuse picked rvec/tvec — no second solve)
            cv2.aruco.drawDetectedMarkers(bgr, corners, ids)
            if self.estimate_poses and self.camera_matrix is not None:
                # Block D: axes must use the same intrinsics as the PnP solve.
                if self._undistort_map1 is not None and self._K_undist is not None:
                    K_draw = self._K_undist
                    D_draw = self._D_zero
                else:
                    K_draw = self.camera_matrix
                    D_draw = self.dist_coeffs
                for rv, tv, m_len in axes_data:
                    cv2.drawFrameAxes(
                        bgr, K_draw, D_draw,
                        rv, tv, m_len * 0.5)

        # Single-marker acceptance: drop frame if reprojection error indicates
        # an IPPE mirror flip (real flips show err >> 20 px; good solves <= 3 px).
        # Publishing a flipped pose makes vpe_fix gate reject it for xy-jump,
        # which leaves EKF2 without vision during takeoff -> drift / runaway
        # (2026-06-03 incident on drone .2). The smoothing LP and adaptive
        # covariance below cannot mask a 50-cm flip — only refusing the frame
        # at source keeps EKF stable.
        single_marker_ok = True
        if len(map_pose_candidates) == 1 and map_marker_corners:
            corners = map_marker_corners[0]
            xs = corners[:, 0]; ys = corners[:, 1]
            pixel_size = max(float(xs.max() - xs.min()),
                             float(ys.max() - ys.min()))
            ndist = self._normalized_center_dist(corners, msg.width, msg.height)
            err_px = map_marker_errs[0]
            reproj_lim = min(_SINGLE_MARKER_REPROJ_CAP,
                             max(_SINGLE_MARKER_MAX_REPROJ,
                                 _SINGLE_MARKER_REPROJ_FRAC * pixel_size))
            if err_px > reproj_lim:
                single_marker_ok = False
                self.get_logger().warn(
                    'single-marker frame REJECTED (likely IPPE flip): '
                    'id_len=%.2fm pixel=%.0f ndist=%.2f err=%.2fpx > %.1fpx'
                    % (map_marker_lengths[0], pixel_size, ndist, err_px,
                       reproj_lim),
                    throttle_duration_sec=1.0)
            else:
                self.get_logger().info(
                    'single-marker frame: id_len=%.2fm pixel=%.0f ndist=%.2f err=%.2fpx lim=%.1fpx'
                    % (map_marker_lengths[0], pixel_size, ndist, err_px,
                       reproj_lim),
                    throttle_duration_sec=2.0)

        markers_used = len(map_pose_candidates)
        if map_pose_candidates:
            cam_pos = self._publish_fused_map_pose(
                map_pose_candidates, msg.header,
                markers_used=markers_used,
                single_marker_ok=single_marker_ok)
            # If we rejected the frame, count it for vpe_fix as no markers used.
            if cam_pos is None:
                markers_used = 0
        else:
            # Vision is silent — drop the lock if it has been quiet long enough so
            # the next preflight has to re-acquire ≥2 markers cleanly.
            t_now = self.get_clock().now().nanoseconds * 1e-9
            if (self._last_pub_t is not None
                    and self._yaw_world_locked
                    and (t_now - self._last_pub_t) > _YAW_RESET_GAP_S):
                self._yaw_world_locked = False
                self._yaw_world = None
                self._yaw_world_lock_start = None
                self.get_logger().info(
                    'aruco_detect: yaw_world unlocked (vision silent > %.1fs)'
                    % _YAW_RESET_GAP_S)

        self._publish_quality_signals(markers_used)

        # Publish markers
        self.markers_pub.publish(markers_msg)

        # Publish debug image
        if self.debug_pub.get_subscription_count() > 0:
            debug_msg = Image()
            debug_msg.header = msg.header
            debug_msg.height = bgr.shape[0]
            debug_msg.width = bgr.shape[1]
            debug_msg.encoding = 'bgr8'
            debug_msg.step = bgr.shape[1] * 3
            debug_msg.data = bgr.tobytes()
            self.debug_pub.publish(debug_msg)

        # Publish map image
        self._publish_map_image(msg.header, detected_ids, cam_pos)

        # ── ROI tracking state update for next frame ─────────────────────────
        # Keep ROIs alive for `track_keepalive_frames` after detection loss so
        # the ROI pass can re-acquire after a brief occlusion / blur burst.
        if ids is not None and len(ids) > 0:
            new_rois = []
            for c in corners:
                try:
                    pts = np.asarray(c).reshape(-1, 2)  # robust to (1,4,2) / (4,2)
                    if pts.shape[0] < 4:
                        continue
                    x_min = float(pts[:, 0].min()); y_min = float(pts[:, 1].min())
                    x_max = float(pts[:, 0].max()); y_max = float(pts[:, 1].max())
                    w = max(self.track_roi_min_px,
                            (x_max - x_min) * self.track_roi_expand)
                    h = max(self.track_roi_min_px,
                            (y_max - y_min) * self.track_roi_expand)
                    cx = (x_min + x_max) * 0.5
                    cy = (y_min + y_max) * 0.5
                    new_rois.append((int(cx - w / 2), int(cy - h / 2),
                                     int(w), int(h)))
                except Exception:
                    continue
            self.prev_marker_rois = new_rois
            self.frames_since_detection = 0
        else:
            self.frames_since_detection += 1
            if self.frames_since_detection > self.track_keepalive_frames:
                self.prev_marker_rois = []


def main(args=None):
    rclpy.init(args=args)
    node = ArucoDetectNode()
    rclpy.spin(node)
    rclpy.shutdown()


if __name__ == '__main__':
    main()
