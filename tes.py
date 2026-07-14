import xml.etree.ElementTree as ET
import re
import os

# --- 1. ノード情報抽出 ---
def parse_transform(transform_str):
    if not transform_str: return 0.0, 0.0
    match = re.search(r'translate\(([^, ]+)[, ]+([^)]+)\)', transform_str)
    if match: return float(match.group(1)), float(match.group(2))
    return 0.0, 0.0

def get_node_bbox_info(node, graph_transform):
    poly = next((child for child in node.iter() if child.tag.endswith('polygon')), None)
    if poly is None: return None
    points = [float(p) for p in re.split(r'[ ,]+', poly.attrib['points'].strip()) if p]
    xs, ys = points[0::2], points[1::2]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    tx, ty = parse_transform(node.attrib.get('transform'))
    gx, gy = graph_transform
    return {'center': [cx + tx + gx, cy + ty + gy], 'size': (w, h)}

def extract_nodes_from_single_file(file_path):
    nodes_data = {}
    tree = ET.parse(file_path)
    root = tree.getroot()
    graph0 = root.find('.//{http://www.w3.org/2000/svg}g[@id="graph0"]')
    g_trans = parse_transform(graph0.attrib.get('transform')) if graph0 is not None else (0.0, 0.0)
    for node in root.findall('.//{http://www.w3.org/2000/svg}g[@class="node"]'):
        title_el = node.find('.//{http://www.w3.org/2000/svg}title')
        if title_el is None or "->" in title_el.text: continue
        text_el = node.find('.//{http://www.w3.org/2000/svg}text')
        display_name = text_el.text if text_el is not None else title_el.text
        bb = get_node_bbox_info(node, g_trans)
        if bb:
            nodes_data[title_el.text] = {**bb, 'name': display_name}
    return nodes_data

def create_svg_time_map(svg_directory):
    files = sorted([f for f in os.listdir(svg_directory) if f.endswith(".svg") and "_opt" not in f])
    return {str(f)[:-4]: extract_nodes_from_single_file(os.path.join(svg_directory, f)) for f in files}, files

# --- 2. 最適化ロジック ---
def optimize_positions(svg_time_map, iterations=1000, k_spring=0.04, repulsion=20000, scale=1.0):
    people = {}
    for t, nodes in svg_time_map.items():
        for name, info in nodes.items():
            if name not in people:
                people[name] = {
                    'pos': list(info['center']),
                    'size': list(info['size']),
                    'name': info['name'],
                    'count': 1
                }
            else:
                people[name]['pos'][0] += info['center'][0]
                people[name]['pos'][1] += info['center'][1]
                people[name]['size'][0] = max(people[name]['size'][0], info['size'][0])
                people[name]['size'][1] = max(people[name]['size'][1], info['size'][1])
                people[name]['count'] += 1
    
    anchors = {name: [p['pos'][0]/p['count'], p['pos'][1]/p['count']] for name, p in people.items()}
    center_x = sum(a[0] for a in anchors.values()) / len(anchors)
    center_y = sum(a[1] for a in anchors.values()) / len(anchors)
    for name in people:
        dx, dy = anchors[name][0] - center_x, anchors[name][1] - center_y
        anchors[name] = [center_x + dx * scale, center_y + dy * scale]
        people[name]['pos'] = list(anchors[name])
    
    names = list(people.keys())
    for _ in range(iterations):
        forces = {name: [0.0, 0.0] for name in names}
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                n1, n2 = names[i], names[j]
                dx = people[n1]['pos'][0] - people[n2]['pos'][0]
                dy = people[n1]['pos'][1] - people[n2]['pos'][1]
                dist = (dx**2 + dy**2)**0.5 or 0.1
                min_dist = (people[n1]['size'][0] + people[n2]['size'][0]) / 2 + 10
                if dist < min_dist:
                    force = repulsion / (dist**2)
                    forces[n1][0] += force * dx / dist; forces[n1][1] += force * dy / dist
                    forces[n2][0] -= force * dx / dist; forces[n2][1] -= force * dy / dist
        for name in names:
            forces[name][0] -= k_spring * (people[name]['pos'][0] - anchors[name][0])
            forces[name][1] -= k_spring * (people[name]['pos'][1] - anchors[name][1])
            people[name]['pos'][0] += forces[name][0]
            people[name]['pos'][1] += forces[name][1]
    return people

# --- 3. SVG出力系 ---
def save_as_svg(people_data, output_path):
    xs = [p['pos'][0] for p in people_data.values()]
    ys = [p['pos'][1] for p in people_data.values()]
    margin = 50
    vb = f"{min(xs)-margin} {min(ys)-margin} {max(xs)-min(xs)+margin*2} {max(ys)-min(ys)+margin*2}"
    dwg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}">']
    for data in people_data.values():
        x, y = data['pos']
        w, h = data['size']
        dwg.append(f'<rect x="{x-w/2}" y="{y-h/2}" width="{w}" height="{h}" fill="#f9f9f9" stroke="#333"/>')
        fs = min(12, h * 0.7)
        dwg.append(f'<text x="{x}" y="{y+fs/3}" font-size="{fs}" text-anchor="middle" font-family="sans-serif">{data["name"]}</text>')
    dwg.append('</svg>')
    with open(output_path, 'w') as f: f.write('\n'.join(dwg))

# --- 実行例 ---
"""
# 1. データセットの作成と最適化
svg_dir = "./svg_data"
svg_time_map, files = create_svg_time_map(svg_dir)
opt_data = optimize_positions(svg_time_map, scale=1.5)

# 2. 全体マップの出力
save_as_svg(opt_data, "master_map.svg")

