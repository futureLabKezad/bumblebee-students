#!/usr/bin/env python3
"""Read-only photo decoding and diagnostic map-to-image homographies."""
import hashlib
import json
import math
from pathlib import Path
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parent
PHOTO=Path('/Users/arsenij/Downloads/5371076751246695215.jpg')
PHOTO_SHA256='99f29423aebcad73c012f1193df54ff3cdc37a9b31aadc2294cd6e4ab99daf47'


def map_rows():
    rows={}
    for line in (ROOT/'map.source.txt').read_text().splitlines():
        values=line.split('#',1)[0].split()
        if not values: continue
        marker=int(values[0]); length,x,y,z,yaw,pitch,roll=map(float,values[1:])
        assert pitch == roll == 0
        c,s=math.cos(yaw),math.sin(yaw)
        rotation=np.array([[c,-s],[s,c]])
        local=np.array([[-length/2,length/2],[length/2,length/2],
                        [length/2,-length/2],[-length/2,-length/2]])
        rows[marker]={'length_m':length,'center_xy_m':[x,y],'yaw_rad':yaw,
                      'corners_xy_m':local@rotation.T+np.array([x,y])}
    return rows


def homography(rows, maps, method):
    known=[row for row in rows if row['id'] in maps]
    source=np.concatenate([maps[row['id']]['corners_xy_m'] for row in known])
    target=np.concatenate([row['corners_pixels'] for row in known]).astype(np.float64)
    matrix,mask=cv2.findHomography(source,target,method,5.0)
    predicted=cv2.perspectiveTransform(source.reshape(-1,1,2),matrix).reshape(-1,2)
    errors=np.linalg.norm(predicted-target,axis=1)
    return {'method':'all_corner_least_squares' if method == 0 else 'RANSAC_5_native_pixels_diagnostic',
        'markers':len(known),'corners':len(source),'matrix':matrix.tolist(),
        'rms_error_pixels':float(np.sqrt(np.mean(errors**2))),
        'median_error_pixels':float(np.median(errors)),'max_error_pixels':float(errors.max()),
        'inlier_corner_count':int(mask.sum()),
        'per_marker':[{'id':row['id'],'mean_error_pixels':float(errors[4*i:4*i+4].mean()),
                       'max_error_pixels':float(errors[4*i:4*i+4].max()),
                       'corner_errors_pixels':errors[4*i:4*i+4].tolist()}
                      for i,row in enumerate(known)]}


def main():
    assert cv2.__version__ == '4.10.0'
    source=PHOTO.read_bytes(); assert hashlib.sha256(source).hexdigest() == PHOTO_SHA256
    bgr=cv2.imread(str(PHOTO)); gray=cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY)
    cv2.setNumThreads(2)
    maps=map_rows(); dictionary=cv2.aruco.getPredefinedDictionary(1)
    profiles=[]
    for name,refinement in [('default_SUBPIX',cv2.aruco.CORNER_REFINE_SUBPIX),
                            ('default_APRILTAG',cv2.aruco.CORNER_REFINE_APRILTAG)]:
        parameters=cv2.aruco.DetectorParameters(); parameters.cornerRefinementMethod=refinement
        corners,ids,rejected=cv2.aruco.ArucoDetector(dictionary,parameters).detectMarkers(gray)
        rows=[{'id':int(marker),'corners_pixels':corner[0].tolist(),
               'mean_corner_center_pixels':corner[0].mean(axis=0).tolist()}
              for marker,corner in zip([] if ids is None else ids.flatten(),corners)]
        profiles.append({'profile':name,'source_gray_sha256':hashlib.sha256(gray.tobytes()).hexdigest(),
            'image_processing':'BGR to gray only; no rescale, CLAHE, mask or photo write',
            'detected_count':len(rows),'rejected_count':len(rejected),'markers':rows,
            'all_corner_homography':homography(rows,maps,0),
            'robust_homography':homography(rows,maps,cv2.RANSAC)})
    # Deterministic preference specified before fitting; never select by map fit.
    merged={row['id']:dict(row,profile='default_APRILTAG') for row in profiles[1]['markers']}
    merged.update({row['id']:dict(row,profile='default_SUBPIX') for row in profiles[0]['markers']})
    merged_rows=sorted(merged.values(),key=lambda row:row['id'])
    layout=[]
    for x in sorted({row['center_xy_m'][0] for row in maps.values()}):
        ids=sorted((marker for marker,row in maps.items() if row['center_xy_m'][0] == x),
                   key=lambda marker:maps[marker]['center_xy_m'][1])
        layout.append({'map_x_m':x,'photo_row_far_to_near':len(layout)+1,
                       'expected_ids_left_to_right':ids,'decoded_ids':[marker for marker in ids if marker in merged]})
    report={'source_photo':str(PHOTO),'source_photo_sha256':PHOTO_SHA256,'opencv':cv2.__version__,
        'numpy':np.__version__,'source_image_pixels':[bgr.shape[1],bgr.shape[0]],'dictionary':'DICT_4X4_100',
        'profiles':profiles,'merged_markers':merged_rows,'merged_count':len(merged_rows),
        'merged_all_corner_homography':homography(merged_rows,maps,0),
        'merged_robust_homography':homography(merged_rows,maps,cv2.RANSAC),
        'map_layout_compared_to_photo':layout,
        'orientation':{'paper_short_side_local_marker_axis':'X','paper_long_side_local_marker_axis':'Y',
            'evidence':'Decoded code corner order plus visually long paper edges along photo depth; '
                       'map Y increases photo left-to-right, map X increases far-to-near',
            'paper_center_assumed':True,'id0_paper_size_estimated':False},
        'limitations':['No camera calibration or lens-distortion correction for owner photo.',
            'Pixel reprojection errors test one planar homography; they do not identify a unique map error.',
            'Homography cannot establish the metric placement of the 415x240 cm perimeter without anchors.',
            'Only ten IDs decode in the two specified raw-gray profiles; other IDs are map expectations.',
            'Glare, paper flatness, corner bias, lens distortion and layout differences remain confounded.',
            'No scale, centers, marker rotations, marker sizes or source image are modified.',
            'Reliable closed paper contour for ID0 is not established; no paper size inferred.']}
    assert hashlib.sha256(PHOTO.read_bytes()).hexdigest() == PHOTO_SHA256
    (ROOT/'photo_analysis.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'decoded_ids':sorted(merged),'layout':layout,
        'merged_all_corner_rms_pixels':report['merged_all_corner_homography']['rms_error_pixels'],
        'merged_all_corner_max_pixels':report['merged_all_corner_homography']['max_error_pixels'],
        'photo_unchanged':True},indent=2))


if __name__ == '__main__':main()
