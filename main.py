import os
import io
import base64
import requests
from bs4 import BeautifulSoup
from PIL import Image
import google.generativeai as genai

# --- 1. CONFIGURACIÓ ---
YUPOO_URL = "https://wavesoccer.x.yupoo.com/albums/7069514?uid=1&isSubCate=false&referrercate=2918263"
# AQUÍ TENIM LA URL DE LA TEVA APP WEB JA INCORPORADA:
WEB_APP_URL = "https://script.google.com/macros/s/AKfycbzMChzqPXGvVClTuqPKyCEBgfXY_BYtyFcPjYRNgxos0PUkcfl-ZCFQCG_7p3yOnBkjpA/exec" 

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://yupoo.com/" 
}

# --- 2. INICIALITZACIÓ IA ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

def es_frontal(image_bytes):
    try:
        img = Image.open(io.BytesIO(image_bytes))
        response = model.generate_content([
            "Aquesta és la imatge d'una samarreta. És la part frontal/davantera principal? Respon només 'SI' o 'NO'.",
            img
        ])
        return "SI" in response.text.upper()
    except Exception as e:
        print(f"⚠️ Error analitzant amb IA. Es descarregarà per seguretat.")
        return True 

def pujar_a_drive(image_bytes, filename):
    try:
        # Convertim la imatge per enviar-la pel pont (Google Apps Script)
        base64_data = base64.b64encode(image_bytes).decode('utf-8')
        payload = {
            "fileName": filename,
            "mimeType": "image/jpeg",
            "fileData": base64_data
        }
        resposta = requests.post(WEB_APP_URL, data=payload)
        return resposta.text
    except Exception as e:
        return f"Error de connexió: {e}"

def main():
    print("Iniciant automatització...")
    
    response = requests.get(YUPOO_URL, headers=HEADERS)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    imatges_tags = soup.find_all('img')
    urls_imatges = []
    
    for img in imatges_tags:
        src = img.get('data-origin-src') or img.get('src')
        if src:
            if src.startswith('//'):
                src = 'https:' + src
            if 'yupoo.com' in src:
                urls_imatges.append(src)
                
    print(f"Trobades {len(urls_imatges)} imatges noves pendents de processar.")

    for i, img_url in enumerate(urls_imatges, 1):
        print(f"Analitzant imatge {i}/{len(urls_imatges)}...")
        
        img_res = requests.get(img_url, headers=HEADERS)
        
        if img_res.status_code != 200:
            print(f"⚠️ La web no ha retornat una imatge vàlida. Status: {img_res.status_code}")
            continue
            
        image_bytes = img_res.content

        if es_frontal(image_bytes):
            print("✅ És frontal o hi ha dubte. Pujant a Google Drive...")
            resultat = pujar_a_drive(image_bytes, f'Novedad_Frontal_{i}.jpg')
            
            if "OK" in resultat:
                print("⬆️ Pujada correctament a la carpeta Novedades!")
            else:
                print(f"❌ Error al pujar: {resultat}")
        else:
            print("❌ No és frontal. Descartada.")

if __name__ == "__main__":
    main()
