import os
import sys
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from src.core.parsers.json_parser import JsonParser

def debug_sound_leaks(project_root: str, target_sound_name: str):
    """
    Belirtilen projede tüm JSON ve JS dosyalarını tarayarak, hedef ses 
    dosyasının (örn. "Cursor1") yanlışlıkla çıkarılıp çıkarılmadığını raporlar.
    """
    print(f"\n[DEBUG] '{target_sound_name}' için sızıntı analizi başlatılıyor...")
    print(f"[DEBUG] Proje Dizini: {project_root}")
    
    parser = JsonParser(translate_notes=True, translate_comments=True)
    
    # 1. Klasörleri Bul (Data ve js)
    data_dir = os.path.join(project_root, "www", "data")
    if not os.path.exists(data_dir):
        data_dir = os.path.join(project_root, "data") # VX Ace veya diğer formatlar
        
    js_dir = os.path.join(project_root, "www", "js")
    if not os.path.exists(js_dir):
        js_dir = os.path.join(project_root, "js")

    files_to_scan = []
    
    # Data dosyaları
    if os.path.exists(data_dir):
        for f in os.listdir(data_dir):
            if f.endswith(".json"):
                files_to_scan.append(os.path.join(data_dir, f))
                
    # plugins.js
    if os.path.exists(js_dir):
        plugins_js = os.path.join(js_dir, "plugins.js")
        if os.path.exists(plugins_js):
            files_to_scan.append(plugins_js)

    total_leaks = 0
    # Tarama İşlemi
    for file_path in files_to_scan:
        try:
            entries = parser.extract_text(file_path)
            
            file_leaks = []
            for path_key, text, context_tag in entries:
                # Sadece tam eşleşme veya boşluksuz içeren durumları ara
                # Eğer "Cursor1" haricinde metinler varsa (örn "Cursor1 is a sound") sızıntı değildir
                if target_sound_name.lower() in text.lower() and len(text.strip()) < len(target_sound_name) + 5:
                    file_leaks.append((path_key, text, context_tag))
            
            if file_leaks:
                print(f"\n[!] SIZINTI TESPİT EDİLDİ: {os.path.basename(file_path)}")
                for path, txt, tag in file_leaks:
                    print(f"    -> Yol (Path): {path}\n    -> Çıkarılan Metin: '{txt}'\n    -> Etiket: {tag}")
                    total_leaks += 1
                    
        except Exception as e:
            print(f"[HATA] {os.path.basename(file_path)} okunurken hata: {e}")

    print(f"\n[SONUÇ] Toplam {total_leaks} potansiyel sızıntı bulundu.")
    if total_leaks == 0:
        print("[BAŞARILI] Belirtilen ses dosyası ismi çeviri havuzuna sızmıyor!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ses dosyası isimlerinin çeviriye sızıp sızmadığını test eder.")
    parser.add_argument("project_path", nargs="?", default=".", help="RPG Maker proje dizini")
    parser.add_argument("--sound", default="Cursor1", help="Aranacak ses dosyası string'i (örn. Cursor1)")
    
    args = parser.parse_args()
    
    project_path = os.path.abspath(args.project_path)
    debug_sound_leaks(project_path, args.sound)
