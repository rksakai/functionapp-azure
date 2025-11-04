import azure.functions as func
import logging
import requests
import json
from datetime import datetime
from typing import Dict, Optional
import os

app = func.FunctionApp()


@app.route(route="weather-data", auth_level=func.AuthLevel.ANONYMOUS, methods=["GET"])
def get_weather_data(req: func.HttpRequest) -> func.HttpResponse:
    """
    Azure Function para buscar dados climáticos em tempo real
    
    Parâmetros:
    - city: Nome da cidade (ex: São Paulo, Rio de Janeiro)
    - country: Código do país (padrão: BR)
    - lang: Idioma (pt_br, en) - padrão: pt_br
    - format: html/json (padrão: html)
    """
    logging.info('🌤️ Requisição de dados climáticos recebida')
    
    try:
        # Parâmetros da requisição
        city = req.params.get('city', 'São Paulo')
        country = req.params.get('country', 'BR')
        lang = req.params.get('lang', 'pt_br')
        response_format = req.params.get('format', 'html').lower()
        
        # Busca dados climáticos
        weather_data = fetch_weather_data(city, country, lang)
        
        if not weather_data.get('success', False):
            error_msg = weather_data.get('error', 'Erro desconhecido')
            if response_format == 'json':
                return func.HttpResponse(
                    body=json.dumps({'error': error_msg}, indent=2),
                    mimetype="application/json",
                    status_code=400
                )
            else:
                return func.HttpResponse(
                    f"<h1>Erro</h1><p>{error_msg}</p>",
                    mimetype="text/html",
                    status_code=400
                )
        
        if response_format == 'json':
            return func.HttpResponse(
                body=json.dumps(weather_data, indent=2, ensure_ascii=False),
                mimetype="application/json",
                status_code=200,
                headers={'Content-Type': 'application/json; charset=utf-8'}
            )
        else:
            # Retorna página HTML
            html_content = generate_weather_html(weather_data, city)
            return func.HttpResponse(
                body=html_content,
                mimetype="text/html",
                status_code=200,
                headers={'Content-Type': 'text/html; charset=utf-8'}
            )
            
    except Exception as e:
        logging.error(f'❌ Erro: {str(e)}')
        
        if response_format == 'json':
            return func.HttpResponse(
                body=json.dumps({'error': str(e)}, indent=2),
                mimetype="application/json",
                status_code=500
            )
        else:
            return func.HttpResponse(
                f"<h1>Erro ao buscar dados</h1><p>{str(e)}</p>",
                mimetype="text/html",
                status_code=500
            )


def fetch_weather_data(city: str, country: str, lang: str) -> Dict:
    """
    Busca dados climáticos de múltiplas APIs
    Usa OpenWeatherMap como fonte principal
    """
    logging.info(f'🔍 Buscando dados climáticos para {city}, {country}')
    
    # Chave da API - Configure nas Application Settings do Azure
    # OPENWEATHER_API_KEY=sua_chave_aqui
    api_key = os.environ.get('OPENWEATHER_API_KEY', 'demo')
    
    if api_key == 'demo':
        logging.warning('⚠️ Usando dados de demonstração. Configure OPENWEATHER_API_KEY.')
        return get_demo_weather_data(city, country)
    
    try:
        # 1. Busca dados atuais (OpenWeatherMap)
        current_url = f"https://api.openweathermap.org/data/2.5/weather"
        current_params = {
            'q': f'{city},{country}',
            'appid': api_key,
            'units': 'metric',
            'lang': 'pt_br'
        }
        
        current_response = requests.get(current_url, params=current_params, timeout=10)
        
        if current_response.status_code != 200:
            return {
                'success': False,
                'error': f'Cidade não encontrada ou erro na API: {current_response.status_code}'
            }
        
        current_data = current_response.json()
        
        # 2. Busca previsão de 5 dias
        forecast_url = f"https://api.openweathermap.org/data/2.5/forecast"
        forecast_params = {
            'q': f'{city},{country}',
            'appid': api_key,
            'units': 'metric',
            'lang': 'pt_br',
            'cnt': 40  # 5 dias (8 previsões por dia)
        }
        
        forecast_response = requests.get(forecast_url, params=forecast_params, timeout=10)
        forecast_data = forecast_response.json() if forecast_response.status_code == 200 else {}
        
        # 3. Busca qualidade do ar (Air Pollution)
        air_url = f"https://api.openweathermap.org/data/2.5/air_pollution"
        air_params = {
            'lat': current_data['coord']['lat'],
            'lon': current_data['coord']['lon'],
            'appid': api_key
        }
        
        air_response = requests.get(air_url, params=air_params, timeout=10)
        air_data = air_response.json() if air_response.status_code == 200 else {}
        
        # Processa dados
        weather_result = process_weather_data(current_data, forecast_data, air_data)
        weather_result['success'] = True
        
        logging.info(f'✅ Dados obtidos para {city}: {weather_result["current"]["temperature"]}°C')
        
        return weather_result
        
    except requests.exceptions.Timeout:
        return {'success': False, 'error': 'Timeout ao buscar dados da API'}
    except requests.exceptions.RequestException as e:
        return {'success': False, 'error': f'Erro de conexão: {str(e)}'}
    except Exception as e:
        return {'success': False, 'error': f'Erro ao processar dados: {str(e)}'}


def process_weather_data(current: Dict, forecast: Dict, air: Dict) -> Dict:
    """Processa e estrutura os dados das APIs"""
    
    # Dados atuais
    current_weather = {
        'temperature': round(current['main']['temp'], 1),
        'feels_like': round(current['main']['feels_like'], 1),
        'temp_min': round(current['main']['temp_min'], 1),
        'temp_max': round(current['main']['temp_max'], 1),
        'pressure': current['main']['pressure'],
        'humidity': current['main']['humidity'],
        'description': current['weather'][0]['description'].capitalize(),
        'icon': current['weather'][0]['icon'],
        'wind_speed': round(current['wind']['speed'] * 3.6, 1),  # m/s para km/h
        'wind_deg': current['wind'].get('deg', 0),
        'clouds': current['clouds']['all'],
        'visibility': current.get('visibility', 0) / 1000,  # metros para km
        'sunrise': datetime.fromtimestamp(current['sys']['sunrise']).strftime('%H:%M'),
        'sunset': datetime.fromtimestamp(current['sys']['sunset']).strftime('%H:%M'),
        'country': current['sys']['country'],
        'city': current['name']
    }
    
    # Adiciona dados de chuva/neve se existirem
    if 'rain' in current:
        current_weather['rain_1h'] = current['rain'].get('1h', 0)
    if 'snow' in current:
        current_weather['snow_1h'] = current['snow'].get('1h', 0)
    
    # Qualidade do ar
    air_quality = {'aqi': 0, 'status': 'Sem dados'}
    if air.get('list'):
        aqi = air['list'][0]['main']['aqi']
        air_quality = {
            'aqi': aqi,
            'status': get_aqi_status(aqi),
            'pm2_5': air['list'][0]['components'].get('pm2_5', 0),
            'pm10': air['list'][0]['components'].get('pm10', 0),
            'o3': air['list'][0]['components'].get('o3', 0),
            'no2': air['list'][0]['components'].get('no2', 0)
        }
    
    # Previsão dos próximos dias (agrupa por dia)
    forecast_daily = []
    if forecast.get('list'):
        days_data = {}
        for item in forecast['list']:
            date = datetime.fromtimestamp(item['dt']).strftime('%Y-%m-%d')
            if date not in days_data:
                days_data[date] = {
                    'temps': [],
                    'descriptions': [],
                    'icons': [],
                    'humidity': [],
                    'rain': 0
                }
            
            days_data[date]['temps'].append(item['main']['temp'])
            days_data[date]['descriptions'].append(item['weather'][0]['description'])
            days_data[date]['icons'].append(item['weather'][0]['icon'])
            days_data[date]['humidity'].append(item['main']['humidity'])
            
            if 'rain' in item:
                days_data[date]['rain'] += item['rain'].get('3h', 0)
        
        for date, data in list(days_data.items())[:5]:
            forecast_daily.append({
                'date': date,
                'weekday': datetime.strptime(date, '%Y-%m-%d').strftime('%A'),
                'temp_min': round(min(data['temps']), 1),
                'temp_max': round(max(data['temps']), 1),
                'description': max(set(data['descriptions']), key=data['descriptions'].count),
                'icon': max(set(data['icons']), key=data['icons'].count),
                'humidity': round(sum(data['humidity']) / len(data['humidity'])),
                'rain': round(data['rain'], 1)
            })
    
    # Previsão horária (próximas 24h)
    forecast_hourly = []
    if forecast.get('list'):
        for item in forecast['list'][:8]:  # Próximas 24h (8 períodos de 3h)
            forecast_hourly.append({
                'time': datetime.fromtimestamp(item['dt']).strftime('%H:%M'),
                'temperature': round(item['main']['temp'], 1),
                'description': item['weather'][0]['description'].capitalize(),
                'icon': item['weather'][0]['icon'],
                'humidity': item['main']['humidity'],
                'wind_speed': round(item['wind']['speed'] * 3.6, 1)
            })
    
    return {
        'current': current_weather,
        'air_quality': air_quality,
        'forecast_daily': forecast_daily,
        'forecast_hourly': forecast_hourly,
        'metadata': {
            'timestamp': datetime.utcnow().isoformat(),
            'source': 'OpenWeatherMap API',
            'update_time': datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        }
    }


def get_aqi_status(aqi: int) -> str:
    """Retorna status da qualidade do ar"""
    statuses = {
        1: 'Boa',
        2: 'Moderada',
        3: 'Prejudicial para grupos sensíveis',
        4: 'Prejudicial',
        5: 'Muito prejudicial'
    }
    return statuses.get(aqi, 'Desconhecido')


def get_demo_weather_data(city: str, country: str) -> Dict:
    """Retorna dados de demonstração quando API key não está configurada"""
    return {
        'success': True,
        'current': {
            'temperature': 24.5,
            'feels_like': 25.2,
            'temp_min': 22.0,
            'temp_max': 28.0,
            'pressure': 1013,
            'humidity': 65,
            'description': 'Parcialmente nublado',
            'icon': '02d',
            'wind_speed': 12.5,
            'wind_deg': 180,
            'clouds': 40,
            'visibility': 10.0,
            'sunrise': '06:15',
            'sunset': '18:45',
            'country': country,
            'city': city
        },
        'air_quality': {
            'aqi': 2,
            'status': 'Moderada',
            'pm2_5': 15.2,
            'pm10': 25.8,
            'o3': 45.3,
            'no2': 18.5
        },
        'forecast_daily': [
            {'date': '2025-11-05', 'weekday': 'Quarta', 'temp_min': 20, 'temp_max': 27, 'description': 'Ensolarado', 'icon': '01d', 'humidity': 60, 'rain': 0},
            {'date': '2025-11-06', 'weekday': 'Quinta', 'temp_min': 21, 'temp_max': 28, 'description': 'Parcialmente nublado', 'icon': '02d', 'humidity': 65, 'rain': 0},
            {'date': '2025-11-07', 'weekday': 'Sexta', 'temp_min': 19, 'temp_max': 25, 'description': 'Chuva leve', 'icon': '10d', 'humidity': 75, 'rain': 2.5},
            {'date': '2025-11-08', 'weekday': 'Sábado', 'temp_min': 18, 'temp_max': 23, 'description': 'Nublado', 'icon': '04d', 'humidity': 70, 'rain': 0},
            {'date': '2025-11-09', 'weekday': 'Domingo', 'temp_min': 20, 'temp_max': 26, 'description': 'Ensolarado', 'icon': '01d', 'humidity': 55, 'rain': 0}
        ],
        'forecast_hourly': [
            {'time': '21:00', 'temperature': 24.5, 'description': 'Céu limpo', 'icon': '01n', 'humidity': 65, 'wind_speed': 10},
            {'time': '00:00', 'temperature': 22.0, 'description': 'Céu limpo', 'icon': '01n', 'humidity': 70, 'wind_speed': 8},
            {'time': '03:00', 'temperature': 20.5, 'description': 'Céu limpo', 'icon': '01n', 'humidity': 75, 'wind_speed': 7},
            {'time': '06:00', 'temperature': 19.8, 'description': 'Parcialmente nublado', 'icon': '02d', 'humidity': 78, 'wind_speed': 9}
        ],
        'metadata': {
            'timestamp': datetime.utcnow().isoformat(),
            'source': 'Dados de Demonstração',
            'update_time': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
            'note': '⚠️ Configure OPENWEATHER_API_KEY para dados reais'
        }
    }


def generate_weather_html(data: Dict, city: str) -> str:
    """Gera página HTML com os dados climáticos"""
    
    current = data['current']
    air = data['air_quality']
    
    # Ícone do tempo
    icon_url = f"https://openweathermap.org/img/wn/{current['icon']}@4x.png"
    
    # Cor do cartão de qualidade do ar
    aqi_colors = {
        'Boa': '#28a745',
        'Moderada': '#ffc107',
        'Prejudicial para grupos sensíveis': '#fd7e14',
        'Prejudicial': '#dc3545',
        'Muito prejudicial': '#6f42c1'
    }
    aqi_color = aqi_colors.get(air['status'], '#6c757d')
    
    # Direção do vento
    wind_directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    wind_dir = wind_directions[round(current['wind_deg'] / 45) % 8]
    
    # Previsão diária
    forecast_daily_html = ""
    for day in data['forecast_daily']:
        rain_html = f"<div class='rain'>💧 {day['rain']}mm</div>" if day['rain'] > 0 else ""
        forecast_daily_html += f"""
        <div class="forecast-day">
            <div class="day-name">{day['weekday'][:3]}</div>
            <div class="day-date">{day['date'][8:]}/{day['date'][5:7]}</div>
            <img src="https://openweathermap.org/img/wn/{day['icon']}@2x.png" alt="{day['description']}">
            <div class="temps">
                <span class="temp-max">{day['temp_max']}°</span>
                <span class="temp-min">{day['temp_min']}°</span>
            </div>
            <div class="description">{day['description'][:20]}</div>
            {rain_html}
        </div>
        """
    
    # Previsão horária
    forecast_hourly_html = ""
    for hour in data['forecast_hourly']:
        forecast_hourly_html += f"""
        <div class="hour-card">
            <div class="hour-time">{hour['time']}</div>
            <img src="https://openweathermap.org/img/wn/{hour['icon']}@2x.png" alt="{hour['description']}">
            <div class="hour-temp">{hour['temperature']}°C</div>
            <div class="hour-wind">💨 {hour['wind_speed']} km/h</div>
        </div>
        """
    
    # Nota de demonstração
    demo_note = ""
    if data['metadata'].get('note'):
        demo_note = f"""
        <div class="demo-warning">
            {data['metadata']['note']}
        </div>
        """
    
    html = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Clima e Tempo - {current['city']}</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }}
            
            .container {{
                max-width: 1200px;
                margin: 0 auto;
            }}
            
            .demo-warning {{
                background: #fff3cd;
                color: #856404;
                padding: 15px;
                border-radius: 12px;
                margin-bottom: 20px;
                text-align: center;
                font-weight: 600;
                border: 2px solid #ffc107;
            }}
            
            .search-bar {{
                background: white;
                padding: 20px;
                border-radius: 16px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                margin-bottom: 20px;
            }}
            
            .search-bar form {{
                display: flex;
                gap: 10px;
                flex-wrap: wrap;
            }}
            
            .search-bar input {{
                flex: 1;
                min-width: 200px;
                padding: 12px 20px;
                border: 2px solid #e0e0e0;
                border-radius: 10px;
                font-size: 1rem;
                transition: border-color 0.3s;
            }}
            
            .search-bar input:focus {{
                outline: none;
                border-color: #667eea;
            }}
            
            .search-bar button {{
                padding: 12px 30px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 1rem;
                font-weight: 600;
                cursor: pointer;
                transition: transform 0.2s;
            }}
            
            .search-bar button:hover {{
                transform: translateY(-2px);
            }}
            
            .main-weather {{
                background: linear-gradient(135deg, rgba(255,255,255,0.95) 0%, rgba(255,255,255,0.9) 100%);
                padding: 40px;
                border-radius: 24px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                margin-bottom: 20px;
                text-align: center;
            }}
            
            .location {{
                font-size: 2rem;
                font-weight: 700;
                color: #2c3e50;
                margin-bottom: 10px;
            }}
            
            .update-time {{
                color: #7f8c8d;
                font-size: 0.9rem;
                margin-bottom: 30px;
            }}
            
            .current-temp {{
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 20px;
                margin: 30px 0;
            }}
            
            .temp-icon img {{
                width: 150px;
                height: 150px;
                filter: drop-shadow(0 4px 8px rgba(0,0,0,0.1));
            }}
            
            .temp-value {{
                font-size: 5rem;
                font-weight: 700;
                color: #2c3e50;
                line-height: 1;
            }}
            
            .temp-unit {{
                font-size: 2rem;
                color: #7f8c8d;
            }}
            
            .weather-description {{
                font-size: 1.5rem;
                color: #34495e;
                margin: 20px 0;
                text-transform: capitalize;
            }}
            
            .feels-like {{
                color: #7f8c8d;
                font-size: 1.1rem;
            }}
            
            .weather-details {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
                margin-top: 30px;
            }}
            
            .detail-card {{
                background: rgba(102, 126, 234, 0.1);
                padding: 20px;
                border-radius: 12px;
                text-align: center;
            }}
            
            .detail-label {{
                color: #7f8c8d;
                font-size: 0.9rem;
                margin-bottom: 8px;
            }}
            
            .detail-value {{
                font-size: 1.5rem;
                font-weight: 700;
                color: #2c3e50;
            }}
            
            .section {{
                background: white;
                padding: 30px;
                border-radius: 16px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                margin-bottom: 20px;
            }}
            
            .section-title {{
                font-size: 1.5rem;
                font-weight: 700;
                color: #2c3e50;
                margin-bottom: 20px;
                padding-bottom: 10px;
                border-bottom: 3px solid #667eea;
            }}
            
            .air-quality {{
                display: flex;
                align-items: center;
                gap: 20px;
                padding: 20px;
                background: {aqi_color};
                color: white;
                border-radius: 12px;
            }}
            
            .aqi-value {{
                font-size: 3rem;
                font-weight: 700;
            }}
            
            .aqi-info {{
                flex: 1;
            }}
            
            .aqi-status {{
                font-size: 1.5rem;
                font-weight: 600;
                margin-bottom: 10px;
            }}
            
            .aqi-components {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
                gap: 10px;
                margin-top: 20px;
            }}
            
            .aqi-component {{
                background: rgba(255,255,255,0.2);
                padding: 10px;
                border-radius: 8px;
                text-align: center;
            }}
            
            .forecast-daily {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                gap: 15px;
            }}
            
            .forecast-day {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 20px;
                border-radius: 12px;
                text-align: center;
            }}
            
            .day-name {{
                font-size: 1.2rem;
                font-weight: 700;
                margin-bottom: 5px;
            }}
            
            .day-date {{
                font-size: 0.9rem;
                opacity: 0.8;
                margin-bottom: 10px;
            }}
            
            .forecast-day img {{
                width: 80px;
                height: 80px;
            }}
            
            .temps {{
                display: flex;
                justify-content: center;
                gap: 10px;
                font-size: 1.3rem;
                font-weight: 700;
                margin: 10px 0;
            }}
            
            .temp-min {{
                opacity: 0.7;
            }}
            
            .description {{
                font-size: 0.85rem;
                opacity: 0.9;
            }}
            
            .rain {{
                margin-top: 10px;
                font-size: 0.9rem;
                background: rgba(255,255,255,0.2);
                padding: 5px;
                border-radius: 5px;
            }}
            
            .forecast-hourly {{
                display: flex;
                gap: 15px;
                overflow-x: auto;
                padding: 10px 0;
            }}
            
            .hour-card {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 15px;
                border-radius: 12px;
                text-align: center;
                min-width: 100px;
            }}
            
            .hour-time {{
                font-weight: 700;
                margin-bottom: 10px;
            }}
            
            .hour-card img {{
                width: 50px;
                height: 50px;
            }}
            
            .hour-temp {{
                font-size: 1.2rem;
                font-weight: 700;
                margin: 10px 0;
            }}
            
            .hour-wind {{
                font-size: 0.85rem;
                opacity: 0.9;
            }}
            
            @media (max-width: 768px) {{
                .current-temp {{
                    flex-direction: column;
                }}
                
                .temp-value {{
                    font-size: 4rem;
                }}
                
                .temp-icon img {{
                    width: 120px;
                    height: 120px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            {demo_note}
            
            <div class="search-bar">
                <form method="GET">
                    <input type="text" name="city" placeholder="Digite uma cidade" value="{city}">
                    <input type="text" name="country" placeholder="País (BR)" value="BR" maxlength="2">
                    <button type="submit">🔍 Buscar</button>
                    <button type="button" onclick="window.location.href='?city={city}&format=json'" style="background: #28a745;">📥 JSON</button>
                </form>
            </div>
            
            <div class="main-weather">
                <div class="location">
                    {current['city']}, {current['country']}
                </div>
                <div class="update-time">
                    Atualizado em {data['metadata']['update_time']}
                </div>
                
                <div class="current-temp">
                    <div class="temp-icon">
                        <img src="{icon_url}" alt="{current['description']}">
                    </div>
                    <div>
                        <span class="temp-value">{current['temperature']}</span>
                        <span class="temp-unit">°C</span>
                    </div>
                </div>
                
                <div class="weather-description">{current['description']}</div>
                <div class="feels-like">Sensação térmica: {current['feels_like']}°C</div>
                
                <div class="weather-details">
                    <div class="detail-card">
                        <div class="detail-label">🌡️ Mínima/Máxima</div>
                        <div class="detail-value">{current['temp_min']}° / {current['temp_max']}°</div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">💧 Umidade</div>
                        <div class="detail-value">{current['humidity']}%</div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">💨 Vento</div>
                        <div class="detail-value">{current['wind_speed']} km/h {wind_dir}</div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">🔭 Visibilidade</div>
                        <div class="detail-value">{current['visibility']} km</div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">☁️ Nuvens</div>
                        <div class="detail-value">{current['clouds']}%</div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">📊 Pressão</div>
                        <div class="detail-value">{current['pressure']} hPa</div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">🌅 Nascer do Sol</div>
                        <div class="detail-value">{current['sunrise']}</div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">🌇 Pôr do Sol</div>
                        <div class="detail-value">{current['sunset']}</div>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <h2 class="section-title">🍃 Qualidade do Ar</h2>
                <div class="air-quality">
                    <div class="aqi-value">{air['aqi']}</div>
                    <div class="aqi-info">
                        <div class="aqi-status">{air['status']}</div>
                        <div>Índice de Qualidade do Ar (AQI)</div>
                    </div>
                </div>
                <div class="aqi-components">
                    <div class="aqi-component">
                        <div style="font-size: 0.8rem; opacity: 0.8;">PM2.5</div>
                        <div style="font-size: 1.2rem; font-weight: 700;">{air.get('pm2_5', 0):.1f}</div>
                    </div>
                    <div class="aqi-component">
                        <div style="font-size: 0.8rem; opacity: 0.8;">PM10</div>
                        <div style="font-size: 1.2rem; font-weight: 700;">{air.get('pm10', 0):.1f}</div>
                    </div>
                    <div class="aqi-component">
                        <div style="font-size: 0.8rem; opacity: 0.8;">O₃</div>
                        <div style="font-size: 1.2rem; font-weight: 700;">{air.get('o3', 0):.1f}</div>
                    </div>
                    <div class="aqi-component">
                        <div style="font-size: 0.8rem; opacity: 0.8;">NO₂</div>
                        <div style="font-size: 1.2rem; font-weight: 700;">{air.get('no2', 0):.1f}</div>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <h2 class="section-title">📅 Previsão dos Próximos 5 Dias</h2>
                <div class="forecast-daily">
                    {forecast_daily_html}
                </div>
            </div>
            
            <div class="section">
                <h2 class="section-title">⏰ Previsão Horária (24h)</h2>
                <div class="forecast-hourly">
                    {forecast_hourly_html}
                </div>
            </div>
            
            <div style="text-align: center; color: white; padding: 20px; font-size: 0.9rem;">
                <p>Dados fornecidos por {data['metadata']['source']}</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html

