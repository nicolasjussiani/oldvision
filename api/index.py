import os
import json
import time
import requests
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = os.getenv('ODDS_API_KEY', '')
BASE_URL = 'https://api.the-odds-api.com/v4/sports'
CACHE_FILE = '/tmp/odds_cache.json'
CACHE_DURATION = 12 * 60 * 60  # 12 horas em segundos

def _fetch_from_api():
    if not API_KEY or API_KEY == 'sua_chave_aqui':
        return {"status": "error", "message": "API Key não configurada no .env", "opportunities": []}

    try:
        response = requests.get(
            f"{BASE_URL}/soccer_brazil_campeonato/odds",
            params={
                'apiKey': API_KEY,
                'regions': 'eu,uk',
                'markets': 'h2h',
                'oddsFormat': 'decimal'
            }
        )
        
        if response.status_code != 200:
             return {"status": "error", "message": f"Falha na The Odds API: {response.text}", "opportunities": []}
             
        data = response.json()
        oportunidades = []

        for match in data:
            bookmakers = match.get('bookmakers', [])
            bet365_data = next((b for b in bookmakers if b['key'] == 'bet365'), None)
            pinnacle_data = next((b for b in bookmakers if b['key'] == 'pinnacle'), None)
            
            if bet365_data and pinnacle_data:
                b365_market = next((m for m in bet365_data['markets'] if m['key'] == 'h2h'), None)
                pin_market = next((m for m in pinnacle_data['markets'] if m['key'] == 'h2h'), None)
                
                if b365_market and pin_market:
                    b365_home_odd = next((o['price'] for o in b365_market['outcomes'] if o['name'] == match['home_team']), 0)
                    pin_away_odd = next((o['price'] for o in pin_market['outcomes'] if o['name'] == match['away_team']), 0)
                    
                    if b365_home_odd > 0 and pin_away_odd > 0:
                        margem = (1 / b365_home_odd) + (1 / pin_away_odd)
                        
                        if margem < 1.0:
                            lucro = ((1 / margem) - 1) * 100
                            oportunidades.append({
                                "id": match['id'],
                                "sport": match['sport_title'],
                                "market": f"{match['home_team']} (Bet365) vs {match['away_team']} (Pinnacle)",
                                "odd_a": b365_home_odd,
                                "odd_b": pin_away_odd,
                                "casa_a": "Bet365",
                                "casa_b": "Pinnacle",
                                "profit": round(lucro, 2),
                                "timestamp": int(time.time())
                            })
                            
        oportunidades.sort(key=lambda x: x["profit"], reverse=True)
        return {"status": "ok", "opportunities": oportunidades}
        
    except Exception as e:
        return {"status": "error", "message": str(e), "opportunities": []}

@app.get("/api/arbitrage")
def get_arbitrage_opportunities():
    # Verifica o cache
    if os.path.exists(CACHE_FILE):
        file_age = time.time() - os.path.getmtime(CACHE_FILE)
        if file_age < CACHE_DURATION:
            # Cache válido (menos de 12 horas), lê do disco
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
                cached_data['message'] = "Carregado do Cache (12h)"
                return cached_data
                
    # Cache inválido ou inexistente, busca na API
    fresh_data = _fetch_from_api()
    
    # Se a chamada foi sucesso, salva no cache
    if fresh_data.get('status') == 'ok':
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(fresh_data, f, ensure_ascii=False, indent=2)
            
    return fresh_data

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
