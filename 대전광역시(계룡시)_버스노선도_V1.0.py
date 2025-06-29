import os, requests, folium
import xml.etree.ElementTree as ET
from folium.plugins import AntPath
from dotenv import load_dotenv

load_dotenv()
SERVICE_KEY = os.getenv('SERVICE_KEY')
BASE_URL = "http://apis.data.go.kr/1613000/BusRouteInfoInqireService"

CITY_CODE = "25"
ROUTE_NO = input('🔍 조회할 대전광역시(계룡시) 버스 노선 번호를 입력하세요: ')

def get_route_list(service_key, city_code, route_no_to_find):
    url = f"{BASE_URL}/getRouteNoList"
    params = {'serviceKey': service_key, 'cityCode': city_code, 'routeNo': route_no_to_find, 'numOfRows': '100', '_type': 'xml'}
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        result_code = root.findtext('.//resultCode')
        if result_code != '00':
            if root.findtext('.//resultMsg') == 'NODATA_ERROR': return []
            else: print(f"API 에러 (get_route_list): {root.findtext('.//resultMsg')}"); return None
        all_found_routes = [{'id': item.findtext('routeid'), 'no': item.findtext('routeno'), 'type': item.findtext('routetp'), 'start': item.findtext('startnodenm'), 'end': item.findtext('endnodenm')} for item in root.findall('.//item')]
        exact_match_routes = [route for route in all_found_routes if route['no'] == route_no_to_find]
        if not exact_match_routes and all_found_routes: print(f"'{ROUTE_NO}'번 버스 정보를 찾을 수 없습니다.")
        return exact_match_routes
    except (requests.exceptions.RequestException, ET.ParseError) as e: print(f"오류 발생 (get_route_list): {e}"); return None

def get_bus_stops(service_key, city_code, route_id):
    url = f"{BASE_URL}/getRouteAcctoThrghSttnList"
    params = {'serviceKey': service_key, 'cityCode': city_code, 'routeId': route_id, 'numOfRows': '500', '_type': 'xml'}
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        result_code = root.findtext('.//resultCode')
        if result_code != '00': print(f"API 에러 (get_bus_stops): {root.findtext('.//resultMsg')}"); return None
        outbound_stops, inbound_stops = [], []
        for item in root.findall('.//item'):
            stop = {'name': item.findtext('nodenm'), 'order': int(item.findtext('nodeord')), 'lat': float(item.findtext('gpslati')), 'lon': float(item.findtext('gpslong'))}
            if item.findtext('updowncd') == '0': outbound_stops.append(stop)
            elif item.findtext('updowncd') == '1': inbound_stops.append(stop)
        outbound_stops.sort(key=lambda x: x['order']); inbound_stops.sort(key=lambda x: x['order'])
        return {'outbound': outbound_stops, 'inbound': inbound_stops}
    except (requests.exceptions.RequestException, ET.ParseError, TypeError, ValueError) as e: print(f"데이터 처리 오류 (get_bus_stops): {e}"); return None

def draw_route_map(stop_data, route_info):
    outbound_stops, inbound_stops = stop_data.get('outbound', []), stop_data.get('inbound', [])
    if not outbound_stops:
        print("지도에 표시할 정류장 정보가 없습니다.")
        return

    # 순환 노선인지 여부를 판단 (inbound 경로가 없으면 순환)
    is_circular = not inbound_stops

    # 지도의 중심을 첫 번째 정류장으로 설정
    m = folium.Map(location=[outbound_stops[0]['lat'], outbound_stops[0]['lon']], zoom_start=12, tiles='CartoDB positron')

    # 상행(기점->종점) 경로 좌표 리스트 생성
    outbound_coords = [(stop['lat'], stop['lon']) for stop in outbound_stops]
    
    # 하행(종점->기점) 경로가 있으면 AntPath로 파란색 경로 추가
    if not is_circular:
        inbound_coords = [(stop['lat'], stop['lon']) for stop in inbound_stops]
        # 상행과 하행 경로를 부드럽게 잇기 위해 상행의 마지막 좌표를 하행의 시작점으로 추가
        if outbound_coords and inbound_coords:
            inbound_coords.insert(0, outbound_coords[-1])
        AntPath(
            locations=inbound_coords,
            tooltip=f"{route_info['no']}번 (종점→기점)",
            use="arrow",
            color="blue",
            pulse_color="#FFFFFF",
            delay=800,
            weight=5,
            dash_array=[10, 20]
        ).add_to(m)

    # 상행 경로는 항상 빨간색으로 추가
    AntPath(
        locations=outbound_coords,
        tooltip=f"{route_info['no']}번 (기점→종점)",
        use="arrow",
        color="red",
        pulse_color="#FFFFFF",
        delay=800,
        weight=5,
        dash_array=[10, 20]
    ).add_to(m)

    # 모든 정류장에 일반 마커 추가
    for stop in (outbound_stops + inbound_stops):
        folium.Marker(
            location=[stop['lat'], stop['lon']],
            popup=f"<b>{stop['name']}</b><br>({stop['order']}번째)",
            tooltip=stop['name'],
            icon=folium.Icon(color='gray', icon='info-sign')
        ).add_to(m)

    # 기점, 종점 또는 순환점 마커 추가
    start_point = outbound_stops[0]
    if is_circular:
        # 순환 노선일 경우, 시작점을 '기/종점'으로 표시
        folium.Marker(
            location=[start_point['lat'], start_point['lon']],
            popup=f"<b>기/종점: {start_point['name']}</b>",
            tooltip="기/종점",
            icon=folium.Icon(color='purple', icon='refresh')
        ).add_to(m)
    else:
        # 일반 왕복 노선일 경우, 기점과 종점 마커를 각각 표시
        # 기점 마커 (초록색)
        folium.Marker(
            location=[start_point['lat'], start_point['lon']],
            popup=f"<b>기점: {start_point['name']}</b>",
            tooltip="기점",
            icon=folium.Icon(color='green', icon='play')
        ).add_to(m)
        
        # 종점 마커 (빨간색) - 상행 경로의 마지막 정류장
        if outbound_stops:
            end_point = outbound_stops[-1]
            folium.Marker(
                location=[end_point['lat'], end_point['lon']],
                popup=f"<b>종점: {end_point['name']}</b>",
                tooltip="종점",
                icon=folium.Icon(color='red', icon='stop')
            ).add_to(m)

    # 버스 종류에 따른 정보창 테두리 색상 설정
    bus_type = route_info['type']
    color_map = {
        '간선버스': 'blue',
        '광역버스': 'red',
        '지선버스': 'green',
        '첨단버스': 'skyblue',
        '급행버스': 'orangered',
        '심야버스': 'black'
    }
    border_color = color_map.get(bus_type, 'grey')

    # 정보창 스타일 (동적 CSS)
    infobox_style = f"""
    <style>
     .info-box {{
         position: fixed;
         bottom: 30px;
         right: 30px;
         z-index: 1000;
         background-color: white;
         padding: 10px;
         border-radius: 5px;
         box-shadow: 3px 3px 5px rgba(0,0,0,0.3);
         font-family: Arial, sans-serif;
         font-size: 14px;
         line-height: 1.6;
         max-width: 300px;
         border: 2px solid {border_color};
     }}
     .info-box h4 {{
         margin: -10px -10px 10px -10px;
         padding: 5px 10px;
         font-size: 18px;
         font-weight: bold;
         background-color: {border_color};
         color: white;
         border-radius: 3px 3px 0 0;
     }}
     .info-box .label {{ font-weight: bold; }}
    </style>
    """

    end_point_name = route_info['end'] if not is_circular else route_info['start']
    infobox_html = f"""
    <div class="info-box">
        <h4>대전광역시(계룡시) {bus_type} {route_info['no']}</h4>
        <p><span class="label">기점:</span> {route_info['start']}</p>
        <p><span class="label">종점:</span> {end_point_name}</p>
    </div>
    """
    m.get_root().html.add_child(folium.Element(infobox_style))
    m.get_root().html.add_child(folium.Element(infobox_html))
    
    # 동적 파일명 생성 및 저장
    city_code, bus_no = route_info['city_code'], route_info['no']
    file_name = f"대전광역시(계룡시)_{bus_type.replace(' ', '_')}_{bus_no}.html"
    m.save(file_name)
    print(f"\n✅ 노선도가 '{file_name}' 파일로 저장되었습니다.")

if __name__ == "__main__":
    if SERVICE_KEY == "YOUR_SERVICE_KEY" or not SERVICE_KEY:
        print("="*60 + "\n🚨 에러: SERVICE_KEY 변수에 인증키를 입력해주세요.\n" + "="*60)
    else:
        print(f"'{ROUTE_NO}'번 버스를 검색합니다.")
        exact_routes = get_route_list(SERVICE_KEY, CITY_CODE, ROUTE_NO)
        if exact_routes is None: print("API 서버와의 통신에 실패했습니다.")
        elif not exact_routes: print(f"'{ROUTE_NO}'번 버스 정보를 찾을 수 없습니다.")
        else:
            selected_route_info = None
            if len(exact_routes) == 1:
                selected_route_info = exact_routes[0]
                print(f"'{ROUTE_NO}'번 버스({selected_route_info['type']})를 찾았습니다.")
            else:
                print(f"'{ROUTE_NO}'번 버스가 {len(exact_routes)}개 있습니다. 하나를 선택해주세요.")
                for i, route in enumerate(exact_routes): print(f" [{i+1}] {route['type']}: {route['start']} ↔ {route['end']}")
                while True:
                    try:
                        choice = int(input("선택할 버스의 번호를 입력하세요: "))
                        if 1 <= choice <= len(exact_routes): selected_route_info = exact_routes[choice - 1]; break
                        else: print("잘못된 번호입니다. 다시 입력해주세요.")
                    except ValueError: print("숫자만 입력해주세요.")
            if selected_route_info:
                selected_route_info['city_code'] = CITY_CODE
                print(f"\n선택된 노선: 대전광역시(계룡시) {selected_route_info['type']} {ROUTE_NO} ({selected_route_info['start']} ↔ {selected_route_info['end']})")
                bus_stop_data = get_bus_stops(SERVICE_KEY, CITY_CODE, selected_route_info['id'])
                if bus_stop_data:
                    draw_route_map(bus_stop_data, selected_route_info)