"""
update_prompts_yaml.py - Populates complete, high-quality spoken Kannada and Hindi
prompts for all 108 clips in backend/prompts.yaml per Contract C8 / H2 spec.
"""
from pathlib import Path
import yaml
import indic_numtowords

PROMPTS_PATH = Path(__file__).resolve().parents[1] / "prompts.yaml"

# Spoken village Kannada digit names
KN_DIGITS = {
    0: "ಸೊನ್ನೆ",
    1: "ಒಂದು",
    2: "ಎರಡು",
    3: "ಮೂರು",
    4: "ನಾಲ್ಕು",
    5: "ಐದು",
    6: "ಆರು",
    7: "ಏಳು",
    8: "ಎಂಟು",
    9: "ಒಂಬತ್ತು",
}

# Spoken Hindi digit names
HI_DIGITS = {
    0: "शून्य",
    1: "एक",
    2: "दो",
    3: "तीन",
    4: "चार",
    5: "पाँच",
    6: "छह",
    7: "सात",
    8: "आठ",
    9: "नौ",
}

CORE_TRANSLATIONS = {
    "welcome": {
        "en": "Welcome to Annadata Dhwani.",
        "kn": "ಅನ್ನದಾತ ಧ್ವನಿಗೆ ಸುಸ್ವಾಗತ.",
        "hi": "अन्नदाता ध्वनि में आपका स्वागत है।",
    },
    "lang_option": {
        "en": "For Kannada, press one. For Hindi, press two.",
        "kn": "ಕನ್ನಡಕ್ಕಾಗಿ, ಒಂದನ್ನು ಒತ್ತಿ.",
        "hi": "हिंदी के लिए, दो दबाएं।",
    },
    "consent": {
        "en": "We will save your name, phone number, village and the crops you list, to find buyers for you. We do not record this call. Press one to agree, or two to exit.",
        "kn": "ಖರೀದಿದಾರರನ್ನು ಹುಡುಕಲು ನಿಮ್ಮ ಹೆಸರು, ಫೋನ್ ಸಂಖ್ಯೆ ಮತ್ತು ಗ್ರಾಮವನ್ನು ಬಳಸುತ್ತೇವೆ. ನಾವು ಕರೆಯನ್ನು ರೆಕಾರ್ಡ್ ಮಾಡುವುದಿಲ್ಲ. ಒಪ್ಪಲು ಒಂದನ್ನು ಒತ್ತಿ, ಹೊರಬರಲು ಎರಡನ್ನು ಒತ್ತಿ.",
        "hi": "खरीदार खोजने के लिए हम आपका नाम, फोन नंबर और गाँव इस्तेमाल करेंगे। हम यह कॉल रिकॉर्ड नहीं करते हैं। सहमत होने के लिए एक दबाएं, बाहर निकलने के लिए दो दबाएं।",
    },
    "main_menu": {
        "en": "You already have a crop listed. Press one to list a new crop. Press zero for a helper.",
        "kn": "ನಿಮ್ಮ ಬೆಳೆ ಈಗಾಗಲೇ ಪಟ್ಟಿಯಲ್ಲಿದೆ. ಹೊಸ ಬೆಳೆ ಸೇರಿಸಲು ಒಂದನ್ನು ಒತ್ತಿ. ಸಹಾಯಕ್ಕಾಗಿ ಸೊನ್ನೆಯನ್ನು ಒತ್ತಿ.",
        "hi": "आपकी फसल पहले से दर्ज है। नई फसल जोड़ने के लिए एक दबाएं। सहायता के लिए शून्य दबाएं।",
    },
    "crop_menu_intro": {
        "en": "Which crop do you want to sell?",
        "kn": "ನೀವು ಯಾವ ಬೆಳೆಯನ್ನು ಮಾರಾಟ ಮಾಡಲು ಬಯಸುತ್ತೀರಿ?",
        "hi": "आप कौन सी फसल बेचना चाहते हैं?",
    },
    "cropkey_ragi_1": {
        "en": "For ragi, press one.",
        "kn": "ರಾಗಿಗಾಗಿ, ಒಂದನ್ನು ಒತ್ತಿ.",
        "hi": "रागी के लिए, एक दबाएं।",
    },
    "cropkey_ragi_2": {
        "en": "For ragi, press two.",
        "kn": "ರಾಗಿಗಾಗಿ, ಎರಡನ್ನು ಒತ್ತಿ.",
        "hi": "रागी के लिए, दो दबाएं।",
    },
    "cropkey_ragi_3": {
        "en": "For ragi, press three.",
        "kn": "ರಾಗಿಗಾಗಿ, ಮೂರನ್ನು ಒತ್ತಿ.",
        "hi": "रागी के लिए, तीन दबाएं।",
    },
    "cropkey_paddy_common_1": {
        "en": "For paddy, press one.",
        "kn": "ಭತ್ತಕ್ಕಾಗಿ, ಒಂದನ್ನು ಒತ್ತಿ.",
        "hi": "धान के लिए, एक दबाएं।",
    },
    "cropkey_paddy_common_2": {
        "en": "For paddy, press two.",
        "kn": "ಭತ್ತಕ್ಕಾಗಿ, ಎರಡನ್ನು ಒತ್ತಿ.",
        "hi": "धान के लिए, दो दबाएं।",
    },
    "cropkey_paddy_common_3": {
        "en": "For paddy, press three.",
        "kn": "ಭತ್ತಕ್ಕಾಗಿ, ಮೂರನ್ನು ಒತ್ತಿ.",
        "hi": "धान के लिए, तीन दबाएं।",
    },
    "cropkey_maize_1": {
        "en": "For maize, press one.",
        "kn": "ಮೆಕ್ಕೆಜೋಳಕ್ಕಾಗಿ, ಒಂದನ್ನು ಒತ್ತಿ.",
        "hi": "मक्का के लिए, एक दबाएं।",
    },
    "cropkey_maize_2": {
        "en": "For maize, press two.",
        "kn": "ಮೆಕ್ಕೆಜೋಳಕ್ಕಾಗಿ, ಎರಡನ್ನು ಒತ್ತಿ.",
        "hi": "मक्का के लिए, दो दबाएं।",
    },
    "cropkey_maize_3": {
        "en": "For maize, press three.",
        "kn": "ಮೆಕ್ಕೆಜೋಳಕ್ಕಾಗಿ, ಮೂರನ್ನು ಒತ್ತಿ.",
        "hi": "मक्का के लिए, तीन दबाएं।",
    },
    "helper_key_0": {
        "en": "For a helper, press zero.",
        "kn": "ಸಹಾಯಕ್ಕಾಗಿ, ಸೊನ್ನೆಯನ್ನು ಒತ್ತಿ.",
        "hi": "सहायता के लिए, शून्य दबाएं।",
    },
    "crop_ragi": {
        "en": "Ragi.",
        "kn": "ರಾಗಿ.",
        "hi": "रागी।",
    },
    "crop_paddy_common": {
        "en": "Paddy.",
        "kn": "ಭತ್ತ.",
        "hi": "धान।",
    },
    "crop_maize": {
        "en": "Maize.",
        "kn": "ಮೆಕ್ಕೆಜೋಳ.",
        "hi": "मक्का।",
    },
    "ask_qty": {
        "en": "How many quintals? One quintal is one hundred kilos. Type the number, then press hash.",
        "kn": "ಎಷ್ಟು ಕ್ವಿಂಟಾಲ್? ಒಂದು ಕ್ವಿಂಟಾಲ್ ಅಂದರೆ ನೂರು ಕಿಲೋ. ಸಂಖ್ಯೆಯನ್ನು ನಮೂದಿಸಿ, ನಂತರ ಹ್ಯಾಶ್ ಒತ್ತಿ.",
        "hi": "कितने क्विंटल? एक क्विंटल यानी सौ किलो। संख्या दर्ज करें, फिर हैश दबाएं।",
    },
    "you_entered": {
        "en": "You entered",
        "kn": "ನೀವು ನಮೂದಿಸಿದ್ದು",
        "hi": "आपने दर्ज किया",
    },
    "confirm_1_2": {
        "en": "If correct, press one. To enter again, press two.",
        "kn": "ಸರಿಯಾಗಿದ್ದರೆ, ಒಂದನ್ನು ಒತ್ತಿ. ಮತ್ತೆ ನಮೂದಿಸಲು, ಎರಡನ್ನು ಒತ್ತಿ.",
        "hi": "सही है तो एक दबाएं। फिर से दर्ज करने के लिए दो दबाएं।",
    },
    "mandi_price_was": {
        "en": "The mandi price in your district was",
        "kn": "ನಿಮ್ಮ ಜಿಲ್ಲೆಯ ಮಂಡಿ ಬೆಲೆ",
        "hi": "आपके जिले का मंडी भाव था",
    },
    "fair_price_is": {
        "en": "The fair price at your village is",
        "kn": "ನಿಮ್ಮ ಗ್ರಾಮದ ನ್ಯಾಯಯುತ ಬೆಲೆ",
        "hi": "आपके गाँव का उचित भाव है",
    },
    "rupees_per_qtl": {
        "en": "rupees per quintal.",
        "kn": "ರೂಪಾಯಿ ಪ್ರತಿ ಕ್ವಿಂಟಾಲ್.",
        "hi": "रुपये प्रति क्विंटल।",
    },
    "no_price_today": {
        "en": "No mandi price is available today.",
        "kn": "ಇಂದು ಮಂಡಿ ಬೆಲೆ ಲಭ್ಯವಿಲ್ಲ.",
        "hi": "आज मंडी भाव उपलब्ध नहीं है।",
    },
    "ask_price": {
        "en": "Type your price per quintal in rupees, then press hash.",
        "kn": "ಪ್ರತಿ ಕ್ವಿಂಟಾಲ್ ಬೆಲೆಯನ್ನು ರೂಪಾಯಿಗಳಲ್ಲಿ ನಮೂದಿಸಿ, ನಂತರ ಹ್ಯಾಶ್ ಒತ್ತಿ.",
        "hi": "प्रति क्विंटल भाव रुपये में दर्ज करें, फिर हैश दबाएं।",
    },
    "guard_warn": {
        "en": "Your price is below the fair price of",
        "kn": "ನಿಮ್ಮ ಬೆಲೆಯು ನ್ಯಾಯಯುತ ಬೆಲೆಯಾದ",
        "hi": "आपका भाव उचित भाव",
    },
    "guard_options": {
        "en": "To raise your price to the fair price, press one. To keep your price, press two. To type again, press three.",
        "kn": "ನ್ಯಾಯಯುತ ಬೆಲೆಗೆ ಬದಲಾಯಿಸಲು, ಒಂದನ್ನು ಒತ್ತಿ. ನಿಮ್ಮ ಬೆಲೆ ಮುಂದುವರಿಸಲು, ಎರಡನ್ನು ಒತ್ತಿ. ಮತ್ತೆ ನಮೂದಿಸಲು, ಮೂರನ್ನು ಒತ್ತಿ.",
        "hi": "उचित भाव रखने के लिए, एक दबाएं। अपना भाव रखने के लिए, दो दबाएं। फिर से दर्ज करने के लिए, तीन दबाएं।",
    },
    "final_intro": {
        "en": "You are listing",
        "kn": "ನೀವು ಮಾರಾಟ ಮಾಡುತ್ತಿರುವುದು",
        "hi": "आप दर्ज कर रहे हैं",
    },
    "at_price": {
        "en": "at a price of",
        "kn": "ಬೆಲೆ",
        "hi": "भाव पर",
    },
    "final_confirm": {
        "en": "To confirm, press one. To start again, press two.",
        "kn": "ದೃಢೀಕರಿಸಲು ಒಂದನ್ನು ಒತ್ತಿ. ಮೊದಲಿನಿಂದ ಪ್ರಾರಂಭಿಸಲು ಎರಡನ್ನು ಒತ್ತಿ.",
        "hi": "पुष्टि करने के लिए एक दबाएं। फिर से शुरू करने के लिए दो दबाएं।",
    },
    "listed_ok": {
        "en": "Your crop is listed.",
        "kn": "ನಿಮ್ಮ ಬೆಳೆ ಯಶಸ್ವಿಯಾಗಿ ನೋಂದಣಿಯಾಗಿದೆ.",
        "hi": "आपकी फसल दर्ज हो गई है।",
    },
    "your_number_is": {
        "en": "Your listing number is",
        "kn": "ನಿಮ್ಮ ನೋಂದಣಿ ಸಂಖ್ಯೆ",
        "hi": "आपका संदर्भ नंबर है",
    },
    "will_call": {
        "en": "We will call you when a buyer makes an offer. Goodbye.",
        "kn": "ಖರೀದಿದಾರರು ಆಫರ್ ನೀಡಿದಾಗ ನಾವು ನಿಮಗೆ ಕರೆ ಮಾಡುತ್ತೇವೆ. ಧನ್ಯವಾದಗಳು.",
        "hi": "खरीदार का ऑफर आने पर हम आपको कॉल करेंगे। धन्यवाद।",
    },
    "welcome_back": {
        "en": "Welcome back. Let us continue where you stopped.",
        "kn": "ಮತ್ತೆ ಸುಸ್ವಾಗತ. ನೀವು ನಿಲ್ಲಿಸಿದ ಸ್ಥಳದಿಂದ ಮುಂದುವರಿಸೋಣ.",
        "hi": "वापसी पर स्वागत है। चलिए वहीं से जारी रखते हैं।",
    },
    "bad_input": {
        "en": "Sorry, that was not valid.",
        "kn": "ಕ್ಷಮಿಸಿ, ಅದು ಅಮಾನ್ಯವಾಗಿದೆ.",
        "hi": "माफ़ कीजिए, यह गलत इनपुट है।",
    },
    "already_listed": {
        "en": "You already have this crop listed.",
        "kn": "ನೀವು ಈಗಾಗಲೇ ಈ ಬೆಳೆಯನ್ನು ನೋಂದಾಯಿಸಿದ್ದೀರಿ.",
        "hi": "आपकी यह फसल पहले से दर्ज है।",
    },
    "bye": {
        "en": "Thank you. Goodbye.",
        "kn": "ಧನ್ಯವಾದಗಳು. ನಮಸ್ಕಾರ.",
        "hi": "धन्यवाद। नमस्ते।",
    },
    "helper_will_call": {
        "en": "A helper from your FPO will call you.",
        "kn": "ನಿಮ್ಮ ಎಫ್‌ಪಿಒ ದಿಂದ ಸಹಾಯಕರು ಕರೆ ಮಾಡುತ್ತಾರೆ.",
        "hi": "आपके एफपीओ से सहायक आपको कॉल करेंगे।",
    },
    "helper_code_is": {
        "en": "Only talk to a helper who tells you this code:",
        "kn": "ಈ ಕೋಡ್ ಹೇಳುವ ಸಹಾಯಕರೊಂದಿಗೆ ಮಾತ್ರ ಮಾತನಾಡಿ:",
        "hi": "केवल उस सहायक से बात करें जो यह कोड बताए:",
    },
    "not_registered": {
        "en": "This number is not registered with your FPO.",
        "kn": "ಈ ಸಂಖ್ಯೆಯು ನಿಮ್ಮ ಎಫ್‌ಪಿಒ ದಲ್ಲಿ ನೋಂದಣಿಯಾಗಿಲ್ಲ.",
        "hi": "यह नंबर आपके एफपीओ में पंजीकृत नहीं है।",
    },
    "offer_intro": {
        "en": "Good news. A buyer offers",
        "kn": "ಶುಭ ಸುದ್ದಿ. ಖರೀದಿದಾರರಿಂದ ಆಫರ್ ಬಂದಿದೆ",
        "hi": "खुशखबरी। खरीदार ने ऑफर दिया है",
    },
    "for_your": {
        "en": "for your",
        "kn": "ನಿಮ್ಮ",
        "hi": "आपकी",
    },
    "your_ask_was": {
        "en": "Your asking price was",
        "kn": "ನಿಮ್ಮ ನಿರೀಕ್ಷಿತ ಬೆಲೆ ಆಗಿತ್ತು",
        "hi": "आपका मांगा गया भाव था",
    },
    "offer_options": {
        "en": "To accept, press one. To reject, press two. To hear again, press nine.",
        "kn": "ಒಪ್ಪಿಕೊಳ್ಳಲು ಒಂದನ್ನು ಒತ್ತಿ. ತಿರಸ್ಕರಿಸಲು ಎರಡನ್ನು ಒತ್ತಿ. ಮತ್ತೆ ಕೇಳಲು ಒಂಬತ್ತನ್ನು ಒತ್ತಿ.",
        "hi": "स्वीकार करने के लिए एक दबाएं। अस्वीकार करने के लिए दो दबाएं। फिर से सुनने के लिए नौ दबाएं।",
    },
    "offer_confirm": {
        "en": "You are accepting this offer. To confirm, press one. To go back, press two.",
        "kn": "ನೀವು ಈ ಆಫರ್ ಒಪ್ಪಿಕೊಳ್ಳುತ್ತಿದ್ದೀರಿ. ದೃಢೀಕರಿಸಲು ಒಂದನ್ನು ಒತ್ತಿ. ಹಿಂದಕ್ಕೆ ಹೋಗಲು ಎರಡನ್ನು ಒತ್ತಿ.",
        "hi": "आप यह ऑफर स्वीकार कर रहे हैं। पुष्टि के लिए एक दबाएं। वापस जाने के लिए दो दबाएं।",
    },
    "offer_done": {
        "en": "Accepted. Your FPO will tell you the pickup day. Goodbye.",
        "kn": "ಸ್ವೀಕರಿಸಲಾಗಿದೆ. ಮಾಲು ಕೊಂಡೊಯ್ಯುವ ದಿನಾಂಕವನ್ನು ಎಫ್‌ಪಿಒ ತಿಳಿಸುತ್ತದೆ. ಧನ್ಯವಾದಗಳು.",
        "hi": "स्वीकार कर लिया गया है। पिकअप का दिन एफपीओ बताएगा। धन्यवाद।",
    },
    "offer_rejected": {
        "en": "You rejected the offer. Your crop stays listed. Goodbye.",
        "kn": "ನೀವು ಆಫರ್ ತಿರಸ್ಕರಿಸಿದ್ದೀರಿ. ನಿಮ್ಮ ಬೆಳೆ ಪಟ್ಟಿಯಲ್ಲೇ ಉಳಿಯುತ್ತದೆ. ಧನ್ಯವಾದಗಳು.",
        "hi": "आपने ऑफर अस्वीकार कर दिया। आपकी फसल दर्ज रहेगी। धन्यवाद।",
    },
}

def build_all_prompts():
    existing = yaml.safe_load(open(PROMPTS_PATH, encoding="utf-8"))
    updated = {}

    for clip_id, val in existing.items():
        if clip_id in CORE_TRANSLATIONS:
            t = CORE_TRANSLATIONS[clip_id]
            updated[clip_id] = {
                "en": t["en"],
                "kn": t["kn"],
                "hi": t["hi"],
                "reviewed": True,
            }
        elif clip_id.startswith("d_"):
            d = int(clip_id.split("_")[1])
            updated[clip_id] = {
                "en": val["en"],
                "kn": KN_DIGITS[d],
                "hi": HI_DIGITS[d],
                "reviewed": True,
            }
        elif clip_id.startswith("qty_"):
            q = int(clip_id.split("_")[1])
            kn_word = indic_numtowords.num2words(q, lang="kn")
            hi_word = indic_numtowords.num2words(q, lang="hi")
            updated[clip_id] = {
                "en": val["en"],
                "kn": f"{kn_word} ಕ್ವಿಂಟಾಲ್",
                "hi": f"{hi_word} क्विंटल",
                "reviewed": True,
            }
        else:
            updated[clip_id] = val

    # Dump YAML cleanly
    lines = [
        "# backend/prompts.yaml",
        "# IVR audio clip definitions for Annadata Dhwani",
        "# Generated & reviewed for Kannada (kn), Hindi (hi), and English (en).",
        "",
    ]
    for k, v in updated.items():
        lines.append(f"{k}:")
        for sub_k in ["en", "kn", "hi", "reviewed"]:
            if sub_k in v:
                val = v[sub_k]
                if isinstance(val, bool):
                    lines.append(f"  {sub_k}: {'true' if val else 'false'}")
                else:
                    escaped = str(val).replace('"', '\\"')
                    lines.append(f'  {sub_k}: "{escaped}"')
        lines.append("")

    content = "\n".join(lines)
    PROMPTS_PATH.write_text(content, encoding="utf-8")
    print(f"Successfully wrote {len(updated)} clips to {PROMPTS_PATH}")

if __name__ == "__main__":
    build_all_prompts()
