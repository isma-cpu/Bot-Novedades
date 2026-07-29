import os
import io
import requests
from bs4 import BeautifulSoup
from PIL import Image
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# --- 1. CONFIGURACIÓ ---
YUPOO_URL = "https://wavesoccer.x.yupoo.com/albums/7069514?uid=1&isSubCate=false&referrercate=2918263"
# POSA AQUÍ L'ID DE LA TEVA CARPETA 'NOVEDADES'
DRIVE_FOLDER_ID = "POSA_L_ID_AQUI" 

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Capçaleres per saltar-nos l'anti-bot de Yupoo (Soluciona l'error 567)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://yupoo.com/" 
}

# --- 2. INICIALITZACIÓ ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash') # Nom del model corregit

SCOPES = ['https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = 'credentials.json' # Assegura't que el nom coincideix amb el teu arxiu de GitHub Actions
creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=creds)

def es_frontal(image_bytes):
    try:
        img = Image.open(io.BytesIO(image_bytes))
        response = model.generate_content([
            "Aquesta és la imatge d'una samarreta. És la part frontal/davantera principal? Respon només 'SI' o 'NO'.",
            img
        ])
        return "SI" in response.text.upper()
    except Exception as e:
        # SI LA IA FALLA, ES DESCARREGA IGUALMENT COM HAS DEMANAT
        print(f"⚠️ Error analitzant amb IA ({e}). Es descarregarà per seguretat.")
        return True 

def main():
    print("Iniciant automatització...")
    
    # 1. Obtenir la web
    response = requests.get(YUPOO_URL, headers=HEADERS)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # 2. Extreure URLs de les fotos (adaptat a l'estructura de Yupoo)
    imatges_tags = soup.find_all('img')
    urls_imatges = []
    
    for img in imatges_tags:
        src = img.get('data-origin-src') or img.get('src')
        if src:
            # Yupoo acostuma a posar URLs començant per '//'
            if src.startswith('//'):
                src = 'https:' + src
            if 'yupoo.com' in src:
                urls_imatges.append(src)
                
    print(f"Trobades {len(urls_imatges)} imatges noves pendents de processar.")

    # 3. Analitzar i pujar
    for i, img_url in enumerate(urls_imatges, 1):
        print(f"Analitzant imatge {i}/{len(urls_imatges)}...")
        
        # Descarregar la foto amb les capçaleres correctes per evitar bloquejos
        img_res = requests.get(img_url, headers=HEADERS)
        
        if img_res.status_code != 200:
            print(f"⚠️ La web no ha retornat una imatge vàlida. Status: {img_res.status_code}")
            continue
            
        image_bytes = img_res.content

        # 4. Validació amb IA i pujada a Drive (amb l'ID de carpeta definit)
        if es_frontal(image_bytes):
            print("✅ És frontal o hi ha dubte. Pujant a Google Drive...")
            file_metadata = {
                'name': f'Novedad_Frontal_{i}.jpg',
                'parents': [DRIVE_FOLDER_ID] # SOLUCIONA L'ERROR DE QUOTA
            }
            media = MediaIoBaseUpload(io.BytesIO(image_bytes), mimetype='image/jpeg', resumable=True)
            
            try:
                drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
                print("⬆️ Pujada correctament a la carpeta Novedades!")
            except Exception as e:
                print(f"❌ Error al pujar a Drive: {e}")
        else:
            print("❌ No és frontal. Descartada.")

if __name__ == "__main__":
    main()
