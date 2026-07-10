#!/usr/bin/env python3
import argparse
import csv
import json
import os
import re

def extract_date_code(file_path):
    """
    timeline.jsonの "file" パス（例: "svg/1333_02.svg"）から
    時期コード（例: "1333_02"）を取り出す関数
    """
    filename = os.path.basename(file_path)
    match = re.search(r'(\d{4}_\d{2})', filename)
    if match:
        return match.group(1)
    return None

def get_next_timeline_event(end_date, timeline_sequence):
    """
    timeline.jsonに存在するイベント順序（ソート済み）の中から、
    キャラクターの退場（史実）時期 'end_date' の「直後にくる未来のイベント」を動的に探す。
    これにより、タイムラインが将来的に増減・並び替えられても、CSVを書き換えることなく
    自動で「次のイベント」で死亡退場枠として抽出されるようになります。
    """
    for t in timeline_sequence:
        if t > end_date:
            return t
    return None

def main():
    parser = argparse.ArgumentParser(description="指定された時期（T）に生存、または死亡・退場するキャラクターをマスターCSVから抽出します。")
    parser.add_argument("character_csv", help="characters.csv のパス")
    parser.add_argument("timeline_json", help="timeline.json のパス")
    parser.add_argument("-d", "--date", required=True, help="抽出対象の時期コード (例: 1333_02)")
    
    args = parser.parse_args()
    target_date = args.date
    output_csv = f"{target_date}.csv"

    # 1. timeline.json を読み込んで、時系列順の時期コードリストを作成・ソート
    try:
        with open(args.timeline_json, "r", encoding="utf-8") as f:
            timeline_data = json.load(f)
    except Exception as e:
        print(f"エラー: {args.timeline_json} の読み込みに失敗しました: {e}")
        return

    timeline_sequence = []
    for event in timeline_data:
        code = extract_date_code(event.get("file", ""))
        if code:
            timeline_sequence.append(code)
    
    # 昇順ソート (1324_09, 1326_03, 1331_08, ...)
    timeline_sequence.sort()

    if target_date not in timeline_sequence:
        print(f"警告: 指定された日付 {target_date} は {args.timeline_json} のタイムライン上に存在しません。")

    # 2. characters.csv を読み込んでフィルタリング
    try:
        with open(args.character_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            rows = list(reader)
    except Exception as e:
        print(f"エラー: {args.character_csv} の読み込みに失敗しました: {e}")
        return

    extracted_rows = []
    survival_count = 0
    death_count = 0

    for row in rows:
        # 空行などのスキップ
        if not row.get("ID"):
            continue
            
        start_date = row.get("登場開始", "").strip()
        end_date = row.get("退場", "").strip()
        
        if not start_date or not end_date:
            continue

        # 判定A: 通常生存
        # 登場開始 <= target_date <= 退場(史実)
        is_surviving = (start_date <= target_date) and (target_date <= end_date)

        # 判定B: 死亡・退場（史実の退場日の「次のタイムラインイベント」が現在の表示時期と一致するか）
        next_event = get_next_timeline_event(end_date, timeline_sequence)
        is_exiting = (next_event == target_date)

        if is_surviving or is_exiting:
            extracted_rows.append(row)
            if is_surviving:
                survival_count += 1
            else:
                death_count += 1

    # 3. 結果を CSV に出力
    try:
        with open(output_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(extracted_rows)
        print(f"成功: {output_csv} に登場人物を抽出しました。")
        print(f"      生存メンバー: {survival_count} 名")
        print(f"      死亡・退場枠  : {death_count} 名")
        print(f"      合計          : {len(extracted_rows)} 名")
    except Exception as e:
        print(f"エラー: {output_csv} の書き込みに失敗しました: {e}")

if __name__ == "__main__":
    main()
