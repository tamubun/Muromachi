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

import math

def get_intersection(s_pos, d_pos, w, h):
    """ノードの中心から辺までの交点を計算する"""
    dx, dy = d_pos[0] - s_pos[0], d_pos[1] - s_pos[1]
    if dx == 0 and dy == 0: return s_pos
    
    # 矩形の半幅、半高
    hw, hh = w / 2, h / 2
    
    # 交点の比率を求める
    ratio = min(abs(hw / dx) if dx != 0 else float('inf'), 
                abs(hh / dy) if dy != 0 else float('inf'))
    
    return s_pos[0] + dx * ratio, s_pos[1] + dy * ratio

def create_arrowhead_poly(x, y, angle, size=10):
    """矢印の先端をpolygonで生成する"""
    # 矢印の先端を基準に、3点を計算
    p1 = (x, y)
    p2 = (x + size * math.cos(angle + math.pi * 0.8), y + size * math.sin(angle + math.pi * 0.8))
    p3 = (x + size * math.cos(angle - math.pi * 0.8), y + size * math.sin(angle - math.pi * 0.8))
    
    points = f"{p1[0]:.2f},{p1[1]:.2f} {p2[0]:.2f},{p2[1]:.2f} {p3[0]:.2f},{p3[1]:.2f}"
    return f'<polygon points="{points}" fill="inherit" stroke="none"/>'

def draw_edge(s_pos, d_pos, src_w, src_h, dst_w, dst_h, stroke, width):
    """端点を調整し、polygonの矢印付きエッジを描画する"""
    start = get_intersection(s_pos, d_pos, src_w, src_h)
    end = get_intersection(d_pos, s_pos, dst_w, dst_h)
    
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    
    line = f'<line x1="{start[0]:.2f}" y1="{start[1]:.2f}" x2="{end[0]:.2f}" y2="{end[1]:.2f}" stroke="{stroke}" stroke-width="{width}"/>'
    # polygonの矢印を追加
    arrow = create_arrowhead_poly(end[0], end[1], angle)
    
    return f'<g stroke="{stroke}" fill="{stroke}">{line}{arrow}</g>'

def get_viewBox(people_data):
    xs = [p['pos'][0] for p in people_data.values()]
    ys = [p['pos'][1] for p in people_data.values()]
    margin = 50
    vb = f"{min(xs)-margin} {min(ys)-margin} {max(xs)-min(xs)+margin*2} {max(ys)-min(ys)+margin*2}"
    return vb

def save_as_svg(people_data, output_path):
    vb = get_viewBox(people_data)
    dwg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}">']
    for data in people_data.values():
        x, y = data['pos']
        w, h = data['size']
        dwg.append(f'<rect x="{x-w/2}" y="{y-h/2}" width="{w}" height="{h}" fill="#f9f9f9" stroke="#333"/>')
        fs = min(12, h * 0.7)
        dwg.append(f'<text x="{x}" y="{y+fs/3}" font-size="{fs}" text-anchor="middle" font-family="sans-serif">{data["name"]}</text>')
    dwg.append('</svg>')
    with open(output_path, 'w') as f: f.write('\n'.join(dwg))

def extract_svg_info(svg_path):
    """オリジナルSVGからノードとエッジ情報を抽出する"""
    tree = ET.parse(svg_path)
    root = tree.getroot()
    ns = {'svg': 'http://www.w3.org/2000/svg', 'xlink': 'http://www.w3.org/1999/xlink'}
    
    nodes_info = {}
    for node in root.findall('.//svg:g[@class="node"]', ns):
        title = node.find('.//svg:title', ns).text
        nodes_info[title] = {
            'a_attrs': node.find('.//svg:a', ns).attrib if node.find('.//svg:a', ns) is not None else {},
            'poly_attrs': node.find('.//svg:polygon', ns).attrib if node.find('.//svg:polygon', ns) is not None else {},
            'text_attrs': node.find('.//svg:text', ns).attrib if node.find('.//svg:text', ns) is not None else {},
            'text_content': node.find('.//svg:text', ns).text if node.find('.//svg:text', ns) is not None else ""
        }

    edges_info = []
    for edge in root.findall('.//svg:g[@class="edge"]', ns):
        title = edge.find('.//svg:title', ns).text
        if title and '->' in title:
            src, dst = title.split('->')
            edges_info.append({
                'src': src, 'dst': dst,
                'path_attrs': edge.find('.//svg:path', ns).attrib if edge.find('.//svg:path', ns) is not None else {},
                'a_attrs': edge.find('.//svg:a', ns).attrib if edge.find('.//svg:a', ns) is not None else {}
            })
            
    return nodes_info, edges_info

import xml.etree.ElementTree as ET
import os
import math

def get_intersection(s_pos, d_pos, w, h):
    """ノードの中心から辺までの交点を計算する"""
    dx, dy = d_pos[0] - s_pos[0], d_pos[1] - s_pos[1]
    if dx == 0 and dy == 0: return s_pos
    hw, hh = w / 2, h / 2
    ratio = min(abs(hw / dx) if dx != 0 else float('inf'), 
                abs(hh / dy) if dy != 0 else float('inf'))
    return s_pos[0] + dx * ratio, s_pos[1] + dy * ratio

def create_arrowhead_poly(x, y, angle, size=10):
    """矢印の先端をpolygonで生成する"""
    p1 = (x, y)
    p2 = (x + size * math.cos(angle + math.pi * 0.8), y + size * math.sin(angle + math.pi * 0.8))
    p3 = (x + size * math.cos(angle - math.pi * 0.8), y + size * math.sin(angle - math.pi * 0.8))
    points = f"{p1[0]:.2f},{p1[1]:.2f} {p2[0]:.2f},{p2[1]:.2f} {p3[0]:.2f},{p3[1]:.2f}"
    return f'<polygon points="{points}" fill="inherit" stroke="none"/>'

def draw_edge(s_pos, d_pos, src_w, src_h, dst_w, dst_h, stroke, width):
    """端点を調整し、polygon矢印付きエッジを描画する"""
    start = get_intersection(s_pos, d_pos, src_w, src_h)
    end = get_intersection(d_pos, s_pos, dst_w, dst_h)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    line = f'<line x1="{start[0]:.2f}" y1="{start[1]:.2f}" x2="{end[0]:.2f}" y2="{end[1]:.2f}" stroke="{stroke}" stroke-width="{width}"/>'
    arrow = create_arrowhead_poly(end[0], end[1], angle)
    return f'<g stroke="{stroke}" fill="{stroke}">{line}{arrow}</g>'

def reconstruct_svg(time, svg_time_map, people_data, output_path, svg_directory):
    vb = get_viewBox(people_data)
    nodes_info, edges_info = extract_svg_info(os.path.join(svg_directory, f"{time}.svg"))
    
    dwg = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="{vb}">']
    
    # 1. エッジ描画
    for edge in edges_info:
        if edge['src'] in people_data and edge['dst'] in people_data:
            s_data, d_data = people_data[edge['src']], people_data[edge['dst']]
            stroke = edge['path_attrs'].get('stroke', '#000')
            width = edge['path_attrs'].get('stroke-width', '1.0')
            
            a_attrs = "".join([f'{k.replace("{http://www.w3.org/1999/xlink}", "xlink:")}="{v}" ' for k, v in edge['a_attrs'].items()])
            dwg.append(f'  <a {a_attrs}>' if a_attrs else "")
            dwg.append(draw_edge(s_data['pos'], d_data['pos'], s_data['size'][0], s_data['size'][1], d_data['size'][0], d_data['size'][1], stroke, width))
            dwg.append('  </a>' if a_attrs else "")

    # 2. ノード描画
    for name in svg_time_map[time].keys():
        if name in people_data and name in nodes_info:
            info = nodes_info[name]
            pos, (w, h) = people_data[name]['pos'], people_data[name]['size']
            a_attrs = "".join([f'{k.replace("{http://www.w3.org/1999/xlink}", "xlink:")}="{v}" ' for k, v in info['a_attrs'].items()])
            
            dwg.append(f'<g class="node" transform="translate({pos[0]:.2f}, {pos[1]:.2f})">')
            dwg.append(f'  <title>{name}</title>')
            dwg.append(f'  <a {a_attrs}>')
            dwg.append(f'    <polygon points="{-w/2:.2f},{-h/2:.2f} {w/2:.2f},{-h/2:.2f} {w/2:.2f},{h/2:.2f} {-w/2:.2f},{h/2:.2f} {-w/2:.2f},{-h/2:.2f}" ' + 
                       " ".join([f'{k}="{v}"' for k, v in info['poly_attrs'].items() if k != 'points']) + '/>')
            
            t_attrs = " ".join([f'{k}="{v}"' for k, v in info['text_attrs'].items() if k not in {'x', 'y', 'text-anchor'}])
            dwg.append(f'    <text x="0" y="5" text-anchor="middle" {t_attrs}>{info["text_content"]}</text>')
            dwg.append('  </a></g>')
            
    dwg.append('</svg>')
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(dwg))

# --- 実行例 ---

# 1. データセットの作成と最適化
# svg_dir = "./svg_data"
# svg_time_map, files = create_svg_time_map(svg_dir)
# opt_data = optimize_positions(svg_time_map, scale=1.5)

# # 2. 全体マップの出力
# save_as_svg(opt_data, "master_map.svg")

