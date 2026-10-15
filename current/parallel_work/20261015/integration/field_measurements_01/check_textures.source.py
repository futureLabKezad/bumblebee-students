#!/usr/bin/env python3
"""Recognize every generated PNG, including all four rotations."""
import argparse
import json
from pathlib import Path
import hashlib
import cv2
import numpy as np

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--out',type=Path,default=Path(__file__).parent)
a=p.parse_args()
m=json.loads((a.out/'manifest.json').read_text())
assert m['dictionary']=='DICT_4X4_100' and m['dictionary_id']==1
params=cv2.aruco.DetectorParameters()
params.cornerRefinementMethod=cv2.aruco.CORNER_REFINE_APRILTAG
params.minMarkerPerimeterRate=.03
params.adaptiveThreshWinSizeMax=51
detector=cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100),params)
results=[]
for marker in m['markers']:
    path=a.out/marker['texture']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==marker['texture_sha256']
    image=cv2.imread(str(path),cv2.IMREAD_GRAYSCALE)
    for turn in range(4):
        _, ids, _=detector.detectMarkers(np.ascontiguousarray(np.rot90(image,turn)))
        actual=[] if ids is None else ids.flatten().tolist()
        if actual != [marker['id']]: raise RuntimeError(f'{path}: rotation {turn*90}: {actual}')
    results.append(dict(id=marker['id'],rotations_passed=4))
report=dict(opencv=cv2.__version__,dictionary=m['dictionary'],markers_passed=len(results),detections_passed=4*len(results),results=results)
(a.out/'recognition_report.json').write_text(json.dumps(report,indent=2)+'\n')
print(f"PASS: {len(results)}/{len(m['markers'])} markers, {4*len(results)} detections including rotations; OpenCV {cv2.__version__}")
