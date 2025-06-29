import os, requests, folium, xml.etree.ElementTree as ET
from folium.plugins import AntPath
from dotenv import load_dotenv

load_dotenv()
SERVICE_KEY = os.getenv('SERVICE_KEY')
BASE_URL = "http://apis.data.go.kr/1613000/BusRouteInfoInqireService"
CITY_CODE = "25"

def get_route_list(service_key, city_code, route_no_to_find):
    url = f"{BASE_URL}/getRouteNoList"
    params = {'serviceKey': service_key, 'cityCode': city_code, 'routeNo': route_no_to_find, 'numOfRows': '100', '_type': 'xml'}
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        result_code = root.findtext('.//resultCode')
        if result_code != '00':
            msg = root.findtext('.//resultMsg')
            if msg == 'NODATA_ERROR':
                print(f"'{route_no_to_find}'번 버스 정보를 찾을 수 없습니다.")
                return []
            else:
                print(f"API 에러 (get_route_list): {msg}")
                return None
        all_found_routes = [{'id': item.findtext('routeid'), 'no': item.findtext('routeno'), 'type': item.findtext('routetp'), 'start': item.findtext('startnodenm'), 'end': item.findtext('endnodenm')} for item in root.findall('.//item')]
        return [route for route in all_found_routes if route['no'] == route_no_to_find]
    except (requests.exceptions.RequestException, ET.ParseError) as e:
        print(f"오류 발생 (get_route_list): {e}")
        return None

def get_bus_stop_paths(service_key, city_code, route_id):
    url = f"{BASE_URL}/getRouteAcctoThrghSttnList"
    params = {'serviceKey': service_key, 'cityCode': city_code, 'routeId': route_id, 'numOfRows': '500', '_type': 'xml'}
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        if root.findtext('.//resultCode') != '00':
            print(f"API 에러 (get_bus_stop_paths): {root.findtext('.//resultMsg')}")
            return None
        
        path_0, path_1 = [], []
        for item in root.findall('.//item'):
            try:
                stop = {'name': item.findtext('nodenm'), 'order': int(item.findtext('nodeord')), 'lat': float(item.findtext('gpslati')), 'lon': float(item.findtext('gpslong'))}
                if item.findtext('updowncd') == '0': path_0.append(stop)
                elif item.findtext('updowncd') == '1': path_1.append(stop)
            except (TypeError, ValueError):
                continue # 좌표 정보가 누락된 정류장은 건너뜁니다.
        
        path_0.sort(key=lambda x: x['order'])
        path_1.sort(key=lambda x: x['order'])
        return {'path_0': path_0, 'path_1': path_1}
    except (requests.exceptions.RequestException, ET.ParseError) as e:
        print(f"데이터 처리 오류 (get_bus_stop_paths): {e}")
        return None

def draw_route_map(stop_data, route_info):
    outbound_stops, inbound_stops = stop_data.get('outbound', []), stop_data.get('inbound', [])
    if not outbound_stops:
        print("지도에 표시할 정류장 정보가 없습니다.")
        return

    is_circular = not inbound_stops
    map_center = [outbound_stops[0]['lat'], outbound_stops[0]['lon']]
    m = folium.Map(location=map_center, zoom_start=12, tiles='CartoDB positron')

    # 경로 그리기 (하행 먼저 그려서 상행선이 위에 보이도록)
    if not is_circular:
        inbound_coords = [(stop['lat'], stop['lon']) for stop in inbound_stops]
        if outbound_stops and inbound_coords:
            inbound_coords.insert(0, (outbound_stops[-1]['lat'], outbound_stops[-1]['lon']))
        AntPath(locations=inbound_coords, tooltip=f"{route_info['no']}번 (종점→기점)", color="blue", weight=5, dash_array=[10, 20]).add_to(m)

    outbound_coords = [(stop['lat'], stop['lon']) for stop in outbound_stops]
    AntPath(locations=outbound_coords, tooltip=f"{route_info['no']}번 (기점→종점)", color="red", weight=5, dash_array=[10, 20]).add_to(m)

    # 마커 추가
    all_stops = outbound_stops + inbound_stops
    for stop in all_stops:
        folium.Marker(
            location=[stop['lat'], stop['lon']],
            popup=f"<b>{stop['name']}</b><br>({stop['order']}번째)",
            tooltip=stop['name'],
            icon=folium.Icon(color='gray', icon='info-sign')
        ).add_to(m)
    
    # 기점/종점 특별 마커 추가
    start_point = outbound_stops[0]
    if is_circular:
        folium.Marker(location=[start_point['lat'], start_point['lon']], popup=f"<b>기/종점: {start_point['name']}</b>", tooltip="기/종점", icon=folium.Icon(color='purple', icon='refresh')).add_to(m)
    else:
        folium.Marker(location=[start_point['lat'], start_point['lon']], popup=f"<b>기점: {start_point['name']}</b>", tooltip="기점", icon=folium.Icon(color='green', icon='play')).add_to(m)
        
        # 공식 종점 이름으로 정확한 종점 찾기
        official_end_name = route_info['end']
        end_point_candidates = [s for s in outbound_stops if s['name'] == official_end_name]
        end_point = end_point_candidates[0] if end_point_candidates else outbound_stops[-1]
        folium.Marker(location=[end_point['lat'], end_point['lon']], popup=f"<b>종점: {end_point['name']}</b>", tooltip="종점", icon=folium.Icon(color='red', icon='stop')).add_to(m)

    # 정보창 추가
    bus_type = route_info['type']
    color_map = {'간선버스': 'blue',
                 '광역버스': 'red',
                 '지선버스': 'green',
                 '첨단버스': 'skyblue',
                 '급행버스': 'orangered',
                 '심야버스': 'black'}
    border_color = color_map.get(bus_type, 'grey')
    end_point_name = route_info['end'] if not is_circular else route_info['start']

    infobox_html = f"""
    <div style="position: fixed; bottom: 30px; right: 30px; z-index: 1000; background-color: white; padding: 10px; border-radius: 5px; box-shadow: 3px 3px 5px rgba(0,0,0,0.3); font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6; max-width: 300px; border: 2px solid {border_color};">
        <h4 style="margin: -10px -10px 10px -10px; padding: 5px 10px; font-size: 18px; font-weight: bold; background-color: {border_color}; color: white; border-radius: 3px 3px 0 0;">대전광역시(계룡시) {bus_type} {route_info['no']}</h4>
        <p><span style="font-weight: bold;">기점:</span> {route_info['start']}</p>
        <p><span style="font-weight: bold;">종점:</span> {end_point_name}</p>
    </div>
    """
    m.get_root().html.add_child(folium.Element(infobox_html))
    
    file_name = f"대전광역시(계룡시)_{bus_type.replace(' ', '_')}_{route_info['no']}.html"
    m.save(file_name)
    print(f"\n✅ 노선도가 '{file_name}' 파일로 저장되었습니다.")

def main():
    if not SERVICE_KEY or SERVICE_KEY == "YOUR_SERVICE_KEY":
        print("\n🚨 에러: .env 파일에 유효한 SERVICE_KEY를 입력해주세요.\n")
        return

    route_no_input = input('🔍 조회할 대전광역시(계룡시) 버스 노선 번호를 입력하세요: ')
    print(f"'{route_no_input}'번 버스를 검색합니다.")
    exact_routes = get_route_list(SERVICE_KEY, CITY_CODE, route_no_input)
    
    if exact_routes is None:
        print("API 서버와의 통신에 실패했습니다.")
        return
    if not exact_routes:
        return # 에러 메시지는 get_route_list에서 출력됨

    selected_route = None
    if len(exact_routes) == 1:
        selected_route = exact_routes[0]
        print(f"'{selected_route['no']}'번 버스({selected_route['type']})를 찾았습니다.")
    else:
        print(f"'{route_no_input}'번 버스가 {len(exact_routes)}개 있습니다. 하나를 선택해주세요.")
        for i, route in enumerate(exact_routes):
            print(f" [{i+1}] {route['type']}: {route['start']} ↔ {route['end']}")
        while True:
            try:
                choice = int(input("선택할 버스의 번호를 입력하세요: "))
                if 1 <= choice <= len(exact_routes):
                    selected_route = exact_routes[choice - 1]
                    break
                else:
                    print("잘못된 번호입니다. 다시 입력해주세요.")
            except ValueError:
                print("숫자만 입력해주세요.")

    if selected_route:
        selected_route['city_code'] = CITY_CODE # 파일명 생성을 위해 추가
        print(f"\n선택된 노선: {selected_route['type']} {selected_route['no']} ({selected_route['start']} ↔ {selected_route['end']})")
        
        bus_stop_paths = get_bus_stop_paths(SERVICE_KEY, CITY_CODE, selected_route['id'])
        if not bus_stop_paths: return

        path_0, path_1 = bus_stop_paths.get('path_0', []), bus_stop_paths.get('path_1', [])
        is_circular = not path_1
        
        outbound_stops, inbound_stops = path_0, path_1
        
        if not is_circular:
            official_end_name = selected_route['end']
            path_0_stop_names = {stop['name'] for stop in path_0}
            
            if official_end_name not in path_0_stop_names:
                print("[정보] API 상/하행 정보를 종점 기준으로 보정합니다.")
                outbound_stops, inbound_stops = path_1, path_0
        
        corrected_stop_data = {'outbound': outbound_stops, 'inbound': inbound_stops}
        draw_route_map(corrected_stop_data, selected_route)

if __name__ == "__main__":
    main()