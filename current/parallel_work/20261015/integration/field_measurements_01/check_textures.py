#!/usr/bin/env python3
"""Verify actual PNG recognition, physical pixels, SDF and unchanged source."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent


def polygon(marker, width, height):
    x,y,_,roll,pitch,yaw = marker['map_pose']
    assert roll == pitch == 0, 'Overlap check expects the supplied horizontal field'
    c,s = math.cos(yaw),math.sin(yaw)
    rotation=np.array([[c,-s],[s,c]])
    local=np.array([[-width/2,height/2],[width/2,height/2],
                    [width/2,-height/2],[-width/2,-height/2]])
    return np.asarray(local@rotation.T+np.array([x,y]),dtype=np.float64)


def intersection_area(first,second):
    """Double-precision convex clipping; paper angles are almost parallel."""
    points=[np.array(point,dtype=np.float64) for point in first]
    cross=lambda a,b: float(a[0]*b[1]-a[1]*b[0])
    for a,b in zip(second,np.roll(second,-1,axis=0)):
        incoming=points; points=[]
        if not incoming: break
        edge=b-a
        previous=incoming[-1]
        previous_inside=cross(edge,previous-a) <= 1e-12
        for current in incoming:
            inside=cross(edge,current-a) <= 1e-12
            if inside != previous_inside:
                direction=current-previous
                denominator=cross(direction,edge)
                if abs(denominator) > 1e-18:
                    fraction=cross(a-previous,edge)/denominator
                    points.append(previous+fraction*direction)
            if inside: points.append(current)
            previous,previous_inside=current,inside
    if len(points) < 3: return 0.0
    return abs(sum(cross(a,b) for a,b in zip(points,points[1:]+points[:1])))/2


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'generated')
    args=parser.parse_args()
    out=args.out.resolve()
    assert out.is_relative_to(ROOT), 'Write only within this separate candidate'
    assert cv2.__version__ == '4.10.0'
    manifest=json.loads((out/'manifest.json').read_text())
    baseline=json.loads((ROOT/'manifest.source.json').read_text())
    source=json.loads((ROOT/'source_manifest.json').read_text())
    workspace=ROOT.parents[3]
    for name,digest in source['read_only_source_sha256'].items():
        assert hashlib.sha256((workspace/name).read_bytes()).hexdigest() == digest, name
    assert (out/'map.input.txt').read_bytes() == (ROOT/'map.source.txt').read_bytes()
    assert manifest['source_sha256'] == baseline['source_sha256']
    assert manifest['dictionary'] == 'DICT_4X4_100' and manifest['dictionary_id'] == 1
    assert len(manifest['markers']) == len(baseline['markers']) == 20
    assert manifest['z_offset'] == baseline['z_offset'] == .32
    world=ET.parse(out/'default.sdf').getroot().find('world')
    includes={row.findtext('uri'):list(map(float,row.findtext('pose').split())) for row in world.findall('include')}
    assert len(includes) == 20
    dictionary=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100)
    parameters=cv2.aruco.DetectorParameters()
    parameters.cornerRefinementMethod=cv2.aruco.CORNER_REFINE_APRILTAG
    parameters.minMarkerPerimeterRate=.03
    parameters.adaptiveThreshWinSizeMax=51
    detector=cv2.aruco.ArucoDetector(dictionary,parameters)
    cv2.setNumThreads(2)
    results=[]
    for marker,old in zip(manifest['markers'],baseline['markers']):
        assert marker['id'] == old['id'] and marker['length'] == old['length']
        assert marker['map_pose'] == old['map_pose'] and marker['world_pose'] == old['world_pose']
        assert includes['model://aruco_'+str(marker['id'])] == old['world_pose']
        texture=out/marker['texture']
        assert hashlib.sha256(texture.read_bytes()).hexdigest() == marker['texture_sha256']
        image=cv2.imread(str(texture),cv2.IMREAD_GRAYSCALE)
        assert image is not None and set(np.unique(image).tolist()) == {0,255}
        model=ET.parse(texture.parents[2]/'model.sdf').getroot()
        plane=model.find('.//visual[@name="print"]/geometry/plane')
        assert plane.findtext('normal') == '0 0 1'
        width,height=map(float,plane.findtext('size').split())
        collision=list(map(float,model.findtext('.//collision/geometry/box/size').split()))
        assert collision == [width,height,.001]
        assert float(model.findtext('.//visual[@name="print"]/pose').split()[2]) == .0002
        ys,xs=np.where(image == 0)
        left,top,right,bottom=int(xs.min()),int(ys.min()),int(xs.max())+1,int(ys.max())+1
        black_width,black_height=right-left,bottom-top
        assert black_width == black_height
        assert left+right == image.shape[1] and top+bottom == image.shape[0]
        black_physical=[black_width/image.shape[1]*width,black_height/image.shape[0]*height]
        assert all(abs(value-marker['length']) < 1e-14 for value in black_physical)
        assert abs(width/image.shape[1]-height/image.shape[0]) < 1e-15, 'Anisotropic texture pixels'
        mask=image.copy(); mask[top:bottom,left:right]=255
        assert np.all(mask == 255), 'Nonwhite pixels outside the true black-square extent'
        if marker['id'] == 0:
            original=cv2.imread(str(Path(source['source_directory'])/old['texture']),cv2.IMREAD_GRAYSCALE)
            assert np.array_equal(image,original), 'ID0 pixels changed before its paper measurement'
            assert [width,height] == [old['tile_side']]*2
            assert image.shape == (800,800) and black_width == 600
        else:
            expected_paper=[manifest['paper_measurement']['paper_width_local_marker_x_m'],
                            manifest['paper_measurement']['paper_height_local_marker_y_m']]
            assert sorted(expected_paper) == [.30,.42]
            assert marker['length'] == .29 and [width,height] == expected_paper
            expected_pixels=[round(value*2400) for value in expected_paper]
            assert list(image.shape) == expected_pixels[::-1] and black_width == 696
            assert [left,top] == [(value-696)//2 for value in expected_pixels]
            cells=image[top:bottom,left:right].reshape(6,116,6,116)
            assert np.all(cells.min(axis=(1,3)) == cells.max(axis=(1,3)))
        turns=[]
        for turn in range(4):
            _,ids,_=detector.detectMarkers(np.ascontiguousarray(np.rot90(image,turn)))
            actual=[] if ids is None else ids.flatten().tolist()
            assert actual == [marker['id']], (marker['id'],turn*90,actual)
            turns.append({'rotation_degrees':turn*90,'ids':actual})
        results.append({'id':marker['id'],'paper_size_m':[width,height],
            'texture_size_pixels':[image.shape[1],image.shape[0]],'black_square_pixels':[black_width,black_height],
            'black_square_size_m':black_physical,'white_left_right_m':left/image.shape[1]*width,
            'white_top_bottom_m':top/image.shape[0]*height,'rotations':turns})
    papers=[polygon(marker,*marker['paper_size_m']) for marker in manifest['markers']]
    inks=[polygon(marker,marker['length'],marker['length']) for marker in manifest['markers']]
    rectangle=np.array([[-.21,.15],[.21,.15],[.21,-.15],[-.21,-.15]])
    assert abs(intersection_area(rectangle,rectangle)-.126) < 1e-12
    assert abs(intersection_area(rectangle,rectangle+[-.36,0])-.018) < 1e-12
    assert intersection_area(rectangle,rectangle+[.50,0]) == 0
    overlaps=[]; occlusions=[]
    for i,first in enumerate(manifest['markers']):
        for j,second in enumerate(manifest['markers']):
            if i == j: continue
            area=intersection_area(papers[i],inks[j])
            if area > 1e-8:occlusions.append({'paper':first['id'],'ink':second['id'],'area_m2':area})
            if i < j:
                area=intersection_area(papers[i],papers[j])
                if area > 1e-8:overlaps.append({'ids':[first['id'],second['id']],'area_m2':area})
    assert not occlusions, occlusions
    assert manifest['field_measurement'] == {'side_lengths_m':[4.15,2.40],
        'axis_assignment':{'map_x':'depth_2.40_m','map_y':'yellow_tape_4.15_m'},
        'edge_anchor':None,'boundary_rendered':False}
    report={'candidate':True,'opencv':cv2.__version__,'numpy':np.__version__,'dictionary':'DICT_4X4_100',
        'markers_passed':len(results),'detections_passed':4*len(results),'geometry_passed':True,
        'ordinary_measured_papers':19,'id0_legacy_pixels_identical':True,
        'source_field_files_unchanged':True,'map_centers_angles_ids_unchanged':True,
        'paper_center_assumed':True,'paper_orientation_confirmed':manifest['paper_measurement']['orientation_confirmed'],
        'field_boundary_rendered':False,'paper_overlaps':overlaps,'paper_on_foreign_black_square':occlusions,
        'gazebo_executed':False,'candidate_installed':False,'results':results}
    (out/'recognition_geometry_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'PASS: {len(results)} markers, {4*len(results)} rotations; physical pixels exact; '
          f'{len(overlaps)} white-paper overlaps, no foreign black-square occlusion; OpenCV {cv2.__version__}')


if __name__ == '__main__':main()
