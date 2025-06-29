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
        if not exact_match_routes and all_found_routes: print(f"💡 API 검색 결과는 있었지만, '{route_no_to_find}'번과 정확히 일치하는 버스는 없습니다.")
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
    if not outbound_stops: print("지도에 표시할 정류장 정보가 없습니다."); return

    is_circular = not inbound_stops

    m = folium.Map(location=[outbound_stops[0]['lat'], outbound_stops[0]['lon']], zoom_start=12, tiles='CartoDB positron')

    # 경로 및 마커 추가 (이전과 동일)
    outbound_coords = [(stop['lat'], stop['lon']) for stop in outbound_stops]
    if is_circular: outbound_coords.append(outbound_coords[0])
    else:
        inbound_coords = [(stop['lat'], stop['lon']) for stop in inbound_stops]
        if outbound_coords and inbound_coords: outbound_coords.append(inbound_coords[0]);
        AntPath(locations=inbound_coords, tooltip=f"{route_info['no']}번 (종점→기점)", use="arrow", color="blue", pulse_color="#FFFFFF", delay=800, weight=5, dash_array=[10, 20]).add_to(m)
    AntPath(locations=outbound_coords, tooltip=f"{route_info['no']}번 노선", use="arrow", color="red", pulse_color="#FFFFFF", delay=800, weight=5, dash_array=[10, 20]).add_to(m)
    for stop in (outbound_stops + inbound_stops): folium.Marker(location=[stop['lat'], stop['lon']], popup=f"<b>{stop['name']}</b><br>({stop['order']}번째)", tooltip=stop['name'], icon=folium.Icon(color='gray', icon='info-sign')).add_to(m)
    start_point = outbound_stops[0]
    if is_circular: folium.Marker(location=[start_point['lat'], start_point['lon']], popup=f"<b>기/종점: {start_point['name']}</b>", tooltip="기/종점", icon=folium.Icon(color='purple', icon='refresh')).add_to(m)
    else:
        folium.Marker(location=[start_point['lat'], start_point['lon']], popup=f"<b>기점: {start_point['name']}</b>", tooltip="출발", icon=folium.Icon(color='green', icon='play')).add_to(m)
        if inbound_stops: folium.Marker(location=[inbound_stops[0]['lat'], inbound_stops[0]['lon']], popup=f"<b>회차지: {inbound_stops[0]['name']}</b>", tooltip="회차", icon=folium.Icon(color='orange', icon='refresh')).add_to(m)

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

    # 2. 동적 CSS 스타일 생성
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
         border: 2px solid {border_color}; /* 동적 테두리 색상 */
     }}
     .info-box h4 {{
         margin: -10px -10px 10px -10px; /* 상자 위쪽/양옆에 붙이기 */
         padding: 5px 10px;
         font-size: 18px;
         font-weight: bold;
         background-color: {border_color}; /* 동적 배경 색상 */
         color: white; /* 제목 글자색 */
         border-radius: 3px 3px 0 0;
     }}
     .info-box .label {{ font-weight: bold; }}
    </style>
    """

    # 3. 정보창 HTML 내용 구성
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
    # -----------------------------------------------------------------------------
    
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
                print(f"\n선택된 노선: {selected_route_info['type']} ({selected_route_info['start']} ↔ {selected_route_info['end']})")
                bus_stop_data = get_bus_stops(SERVICE_KEY, CITY_CODE, selected_route_info['id'])
                if bus_stop_data:
                    draw_route_map(bus_stop_data, selected_route_info)