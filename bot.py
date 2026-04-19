import os
import ccxt
import google.generativeai as genai
from dotenv import load_dotenv
import time
import json
import traceback

# ==========================================
# 1. CONFIGURACIÓN Y SEGURIDAD
# ==========================================
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "historial_precios.json")

# Configuración de Gemini
GEMINI_KEY = os.getenv("GEMINI_API_KEY") 
genai.configure(api_key=GEMINI_KEY)

# Lista de modelos solicitados (Fallback System)
MODELOS_A_PROBAR = [
    'gemini-3.1-flash-lite-preview', 
    'gemini-3-flash-preview', 
    'gemini-2.5-flash-lite', 
    'gemini-2.5-flash'
]

# Configuración de Binance (Lee las llaves de tu .env)
BN_KEY = os.getenv("BINANCE_API_KEY")
BN_SECRET = os.getenv("BINANCE_SECRET_KEY")

# Conexiones a Binance
exchange_spot = ccxt.binance()
exchange_futures = ccxt.binance({
    'apiKey': BN_KEY,
    'secret': BN_SECRET,
    'options': {'defaultType': 'future'},
    'enableRateLimit': True
})

# ==========================================
# 2. LÓGICA DE DATOS Y LIQUIDEZ
# ==========================================

def calcular_zonas_liquidacion(precio):
    """Calcula niveles teóricos de liquidación según apalancamiento."""
    return {
        "short_100x": precio * 1.005, 
        "short_50x": precio * 1.015,  
        "short_25x": precio * 1.03,   
        "long_100x": precio * 0.995,  
        "long_50x": precio * 0.985,   
        "long_25x": precio * 0.97     
    }

def manejar_memoria(nuevo_registro):
    """Mantiene un historial JSON de los últimos 50 ciclos."""
    historial = []
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                historial = json.load(f)
        except: 
            historial = []

    historial.append(nuevo_registro)
    if len(historial) > 50: 
        historial = historial[-50:]

    with open(DB_FILE, "w") as f:
        json.dump(historial, f, indent=4)
    return historial

def obtener_analisis_ia(precio, cambio, oi, liq_zones, order_book, historial):
    """Consulta los modelos de Gemini uno por uno hasta obtener respuesta."""
    
    prompt = f"""
    Actuá como un experto en Trading Institucional y Liquidez (Order Flow).
    Analizá BTC/USDT para una estrategia de Swing (velas de 1h/4h).

    DATOS DE MERCADO:
    - Precio Spot: {precio} USDT ({cambio}% en 24h)
    - Open Interest: {oi} BTC (Interés del mercado de futuros)
    
    ZONAS DE LIQUIDACIÓN (Magnetos de precio):
    - SHORTS (Arriba): 100x: {liq_zones['short_100x']:.2f} | 50x: {liq_zones['short_50x']:.2f} | 25x: {liq_zones['short_25x']:.2f}
    - LONGS (Abajo): 100x: {liq_zones['long_100x']:.2f} | 50x: {liq_zones['long_50x']:.2f} | 25x: {liq_zones['long_25x']:.2f}

    ORDER BOOK (Muros de órdenes):
    - Bids (Compras): {order_book['bids'][:3]}
    - Asks (Ventas): {order_book['asks'][:3]}

    TENDENCIA RECIENTE (Últimos registros):
    {historial[-5:]}

    FORMATO DE RESPUESTA:
    DECISIÓN: [COMPRAR / VENDER / ESPERAR]
    ZONA DE LIQUIDEZ OBJETIVO: [Hacia qué precio liquidará el mercado]
    ESTRATEGIA: [Entrada, Take Profit, Stop Loss]
    MOTIVO TÉCNICO: [Explicación basada en OI y liquidaciones]
    """

    for nombre_modelo in MODELOS_A_PROBAR:
        try:
            print(f"🤖 Intentando análisis con: {nombre_modelo}...")
            model = genai.GenerativeModel(nombre_modelo)
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            print(f"⚠️ El modelo {nombre_modelo} no está disponible o falló. Intentando el siguiente...")
            continue
    
    return "❌ Error: Ninguno de los modelos seleccionados pudo procesar la solicitud."

# ==========================================
# 3. EJECUCIÓN DEL CICLO
# ==========================================

def ejecutar_bot():
    print(f"\n--- 🔍 Iniciando Análisis de Mercado: {time.strftime('%H:%M:%S')} ---")
    try:
        # 1. Obtener Precio y Variación (Spot)
        ticker = exchange_spot.fetch_ticker('BTC/USDT')
        precio = ticker['last']
        cambio = ticker['percentage']
        
        # 2. Obtener Open Interest (Futures) con manejo de errores robusto
        oi_actual = "N/A"
        try:
            # Bypass directo a la API nativa de Binance Futuros (sin intermediarios)
            datos_crudos = exchange_futures.fapiPublicGetOpenInterest({'symbol': 'BTCUSDT'})
            oi_actual = float(datos_crudos['openInterest'])
        except Exception as e_oi:
            print(f"⚠️ Error OI nativo: {e_oi}")

        # 3. Obtener Order Book
        ob = exchange_spot.fetch_order_book('BTC/USDT')
        
        # 4. Calcular Zonas de Liquidación
        zonas = calcular_zonas_liquidacion(precio)
        
        # 5. Gestionar Memoria
        registro = {
            "fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
            "precio": precio,
            "oi": oi_actual
        }
        historial = manejar_memoria(registro)

        # 6. Consultar a Gemini
        print(f"📊 Datos obtenidos. Consultando IA...")
        analisis = obtener_analisis_ia(precio, cambio, oi_actual, zonas, ob, historial)
        
        print("\n" + "="*75)
        print(analisis)
        print("="*75 + "\n")

    except Exception as e:
        print(f"❗ Error grave en el ciclo: {e}")
        # Esto te dirá exactamente en qué línea falló si vuelve a pasar
        traceback.print_exc()

# ==========================================
# 4. BUCLE PRINCIPAL
# ==========================================

if __name__ == "__main__":
    print("🚀 Bot de Swing Trading activo.")
    print(f"📂 Guardando historial en: {DB_FILE}")
    print(f"🧠 Modelos configurados: {MODELOS_A_PROBAR}")
    
    while True:
        ejecutar_bot()
        print(f"⏳ Análisis completo. Esperando 1 hora para el próximo ciclo...")
        time.sleep(3600)