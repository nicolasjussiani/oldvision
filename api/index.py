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
        # Busca os próximos jogos gerais (vários esportes) para aumentar a rede
        response = requests.get(
            f"{BASE_URL}/upcoming/odds",
            params={
                'apiKey': API_KEY,
                'regions': 'eu,uk,us',
                'markets': 'h2h',
                'oddsFormat': 'decimal'
            }
        )
        
        if response.status_code != 200:
             return {"status": "error", "message": f"Falha na The Odds API: {response.text}", "opportunities": []}
             
        data = response.json()
        todas_oportunidades = []

        # Para cada partida
        for match in data:
            bookmakers = match.get('bookmakers', [])
            
            # Compara todas as casas de apostas umas contra as outras
            for i in range(len(bookmakers)):
                for j in range(i + 1, len(bookmakers)):
                    bookie_a = bookmakers[i]
                    bookie_b = bookmakers[j]
                    
                    market_a = next((m for m in bookie_a['markets'] if m['key'] == 'h2h'), None)
                    market_b = next((m for m in bookie_b['markets'] if m['key'] == 'h2h'), None)
                    
                    if market_a and market_b and 'home_team' in match and 'away_team' in match:
                        home_odd_a = next((o['price'] for o in market_a['outcomes'] if o['name'] == match['home_team']), 0)
                        away_odd_b = next((o['price'] for o in market_b['outcomes'] if o['name'] == match['away_team']), 0)
                        
                        if home_odd_a > 0 and away_odd_b > 0:
                            margem = (1 / home_odd_a) + (1 / away_odd_b)
                            lucro = ((1 / margem) - 1) * 100
                            
                            todas_oportunidades.append({
                                "id": f"{match['id']}_{bookie_a['key']}_{bookie_b['key']}",
                                "sport": match['sport_title'],
                                "market": f"{match['home_team']} ({bookie_a['title']}) vs {match['away_team']} ({bookie_b['title']})",
                                "odd_a": home_odd_a,
                                "odd_b": away_odd_b,
                                "casa_a": bookie_a['title'],
                                "casa_b": bookie_b['title'],
                                "profit": round(lucro, 2),
                                "timestamp": int(time.time())
                            })
                            
        # Ordena pelo maior lucro
        todas_oportunidades.sort(key=lambda x: x["profit"], reverse=True)
        
        # Filtra as oportunidades com lucro real (> 0)
        oportunidades_reais = [o for o in todas_oportunidades if o["profit"] > 0]
        
        # Se não tiver NENHUMA arbitragem real no mundo agora, pegamos as top 5 com as menores perdas
        # para a tela nunca ficar vazia, como o usuário pediu.
        if len(oportunidades_reais) == 0:
            oportunidades = todas_oportunidades[:5]
        else:
            oportunidades = oportunidades_reais
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
