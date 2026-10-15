#!/usr/bin/env python3
"""Separate field candidate with measured rectangular paper; no installation."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import cv2
import numpy as np

DICTIONARY = 'DICT_4X4_100'
THICKNESS = 0.001
PRINT_GAP = 0.0002
CANDIDATE_ROOT = Path(__file__).resolve().parent
PAPER_PIXELS_PER_METER = 2400
ORDINARY_LENGTH = 0.29


def paper_layout(marker, paper_width, paper_height, margin_cells, cells):
    """The known 29 cm code keeps square physical pixels on measured paper."""
    if marker['id'] != 0 and math.isclose(marker['length'], ORDINARY_LENGTH, abs_tol=1e-12):
        width, height = paper_width, paper_height
        dimensions = [width, height, marker['length']]
        pixels = [round(value*PAPER_PIXELS_PER_METER) for value in dimensions]
        if any(abs(pixel/PAPER_PIXELS_PER_METER-value) > 1e-12 for pixel, value in zip(pixels, dimensions)):
            raise ValueError('Paper dimensions must be exact at 2400 pixels/m')
        pw, ph, black = pixels
        if width <= marker['length'] or height <= marker['length'] or black % cells:
            raise ValueError('Paper must surround the square code; code cells must have integer pixels')
        if (pw-black) % 2 or (ph-black) % 2:
            raise ValueError('Centered white margins must have integer pixels')
        return dict(width=width, height=height, pixels=[pw, ph], black_pixels=black,
                    left=(pw-black)//2, top=(ph-black)//2,
                    policy='owner_measured_ordinary_paper_conditional_orientation')
    # ID0 and other sizes retain the entire legacy square layout unchanged.
    black, pad = cells*100, margin_cells*100
    side = marker['length']*(cells+2*margin_cells)/cells
    return dict(width=side, height=side, pixels=[black+2*pad]*2,
                black_pixels=black, left=pad, top=pad,
                policy='legacy_unmeasured_id0' if marker['id'] == 0 else 'legacy_other_length')

def read_map(path):
    markers = []
    seen = set()
    for n, line in enumerate(path.read_text().splitlines(), 1):
        values = line.split('#', 1)[0].split()
        if not values:
            continue
        if not 4 <= len(values) <= 8:
            raise ValueError(f'Line {n}: expected 4 to 8 columns')
        mid = int(values[0])
        v = list(map(float, values[1:]))
        v += [0.] * (7 - len(v))
        length, x, y, z, yaw, pitch, roll = v
        if mid in seen or not 0 <= mid < 100 or length <= 0 or not all(map(math.isfinite, v)):
            raise ValueError(f'Line {n}: invalid size, ID, duplicate or non-finite value')
        seen.add(mid)
        markers.append(dict(id=mid, length=length, map_pose=[x,y,z,roll,pitch,yaw]))
    if not markers:
        raise ValueError('Empty map')
    return markers

def rotation(pose):
    r,p,y = pose[3:]
    cr,sr,cp,sp,cy,sy = math.cos(r),math.sin(r),math.cos(p),math.sin(p),math.cos(y),math.sin(y)
    return np.array([[cy*cp,cy*sp*sr-sy*cr,cy*sp*cr+sy*sr],
                     [sy*cp,sy*sp*sr+cy*cr,sy*sp*cr-cy*sr],[-sp,cp*sr,cp*cr]])

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--map',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--z-offset',type=float, help='Map to world translation; default puts lowest printed surface at z=0')
    ap.add_argument('--margin-cells',type=int,default=1,help='White margin in marker cells (default 1)')
    ap.add_argument('--paper-width',type=float,default=.30,help='Ordinary paper along local marker X, meters; default matches owner photo')
    ap.add_argument('--paper-height',type=float,default=.42,help='Ordinary paper along local marker Y, meters; default matches owner photo')
    args=ap.parse_args()
    if cv2.__version__ != '4.10.0':
        ap.error('Use the existing vision environment with OpenCV 4.10.0')
    if (args.margin_cells < 1 or (args.z_offset is not None and not math.isfinite(args.z_offset))
            or not all(math.isfinite(value) and value > 0 for value in (args.paper_width,args.paper_height))):
        ap.error('Invalid margin or offset')
    if not args.out.resolve().is_relative_to(CANDIDATE_ROOT):
        ap.error('This candidate writes only within its own field_measurements_01 directory')
    markers=read_map(args.map)
    dictionary=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100)
    cells=dictionary.markerSize+2
    vertices=[]
    for m in markers:
        layout=paper_layout(m,args.paper_width,args.paper_height,args.margin_cells,cells)
        m['paper_layout']=layout
        m['paper_size_m']=[layout['width'],layout['height']]
        hx,hy=layout['width']/2,layout['height']/2
        vertices.extend((rotation(m['map_pose'])@np.array([a,b,0.])+m['map_pose'][:3])
                        for a,b in [(-hx,hy),(hx,hy),(hx,-hy),(-hx,-hy)])
    offset=args.z_offset if args.z_offset is not None else -min(v[2] for v in vertices)
    out=args.out.resolve(); out.mkdir(parents=True,exist_ok=True)
    tree=ET.parse(Path(__file__).with_name('px4_default.template.sdf'))
    world=tree.getroot().find('world')
    # Surface of the printing is z=0; substrate extends down by 1 mm.
    ground=world.find("model[@name='ground_plane']")
    ground.find('pose').text=f'0 0 {-THICKNESS} 0 0 0'
    for system in ['Physics','UserCommands','SceneBroadcaster','Sensors','Imu','AirPressure','Magnetometer','NavSat']:
        slug={'UserCommands':'user-commands','SceneBroadcaster':'scene-broadcaster','AirPressure':'air-pressure','NavSat':'navsat'}.get(system,system.lower())
        plugin=ET.SubElement(world,'plugin',filename=f'gz-sim-{slug}-system',name=f'gz::sim::systems::{system}')
        if system=='Sensors': ET.SubElement(plugin,'render_engine').text='ogre2'
    for m in markers:
        mid=m['id']; name=f'aruco_{mid}'; folder=out/'models'/name
        (folder/'materials/textures').mkdir(parents=True,exist_ok=True)
        layout=m['paper_layout']
        raw=cv2.aruco.generateImageMarker(dictionary,mid,layout['black_pixels'],borderBits=1)
        pw,ph=layout['pixels']; left,top,black=layout['left'],layout['top'],layout['black_pixels']
        tex=np.full((ph,pw),255,dtype=np.uint8)
        tex[top:top+black,left:left+black]=raw
        texture=folder/'materials/textures'/f'marker_{mid}.png'
        if not cv2.imwrite(str(texture),tex): raise OSError(texture)
        width,height=m['paper_size_m']
        (folder/'model.config').write_text(f'<model><name>{name}</name><version>1.0</version><sdf version="1.9">model.sdf</sdf><description>{DICTIONARY}, ID {mid}</description></model>')
        (folder/'model.sdf').write_text(f'''<sdf version="1.9"><model name="{name}"><static>true</static><link name="tile">
<collision name="substrate_collision"><pose>0 0 {-THICKNESS/2} 0 0 0</pose><geometry><box><size>{width} {height} {THICKNESS}</size></box></geometry></collision>
<visual name="substrate_visual"><pose>0 0 {-THICKNESS/2-0.00001} 0 0 0</pose><geometry><box><size>{width} {height} {THICKNESS}</size></box></geometry><material><diffuse>1 1 1 1</diffuse></material></visual>
<visual name="print"><pose>0 0 {PRINT_GAP} 0 0 0</pose><cast_shadows>false</cast_shadows><geometry><plane><normal>0 0 1</normal><size>{width} {height}</size></plane></geometry><material><ambient>1 1 1 1</ambient><diffuse>1 1 1 1</diffuse><specular>0 0 0 1</specular><pbr><metal><albedo_map>model://{name}/materials/textures/marker_{mid}.png</albedo_map><metalness>0</metalness><roughness>1</roughness></metal></pbr></material></visual>
</link></model></sdf>''')
        pose=m['map_pose'].copy(); pose[2]+=offset; m['world_pose']=pose
        m['texture']=str(texture.relative_to(out)); m['texture_sha256']=hashlib.sha256(texture.read_bytes()).hexdigest()
        inc=ET.SubElement(world,'include'); ET.SubElement(inc,'uri').text=f'model://{name}'
        ET.SubElement(inc,'pose').text=' '.join(format(v,'.17g') for v in pose)
    ET.indent(tree); tree.write(out/'default.sdf',encoding='utf-8',xml_declaration=True)
    manifest=dict(dictionary=DICTIONARY,dictionary_id=1,source_map=str(args.map.resolve()),source_sha256=hashlib.sha256(args.map.read_bytes()).hexdigest(),z_offset=offset,thickness=THICKNESS,print_gap=PRINT_GAP,margin_cells=args.margin_cells,
        candidate=True,installed=False,simulator_executed=False,
        paper_measurement=dict(black_square_m=.29,paper_width_local_marker_x_m=args.paper_width,
            paper_height_local_marker_y_m=args.paper_height,
            orientation_confirmed=(args.paper_width == .30 and args.paper_height == .42),
            orientation_source='Owner photo and decoded ID corner order; see photo_analysis.json',
            reference_photo_sha256='99f29423aebcad73c012f1193df54ff3cdc37a9b31aadc2294cd6e4ab99daf47',
            paper_center_assumed=True,id0_paper_size_known=False,pixels_per_meter=PAPER_PIXELS_PER_METER),
        field_measurement=dict(side_lengths_m=[4.15,2.40],
            axis_assignment={'map_x':'depth_2.40_m','map_y':'yellow_tape_4.15_m'},
            edge_anchor=None,boundary_rendered=False),
        markers=markers)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (out/'map.input.txt').write_bytes(args.map.read_bytes())
    print(f'{len(markers)} markers; {DICTIONARY}; z offset {offset:.6f}; {out}/default.sdf')

if __name__=='__main__': main()
