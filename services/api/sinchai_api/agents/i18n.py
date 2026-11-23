"""Farmer-facing phrases in Hindi, Maithili, Bhojpuri and English.

Draft wording for the prototype; every line is marked for native-speaker review in
docs/decisions/0005-languages.md before it is played to farmers.
"""

from __future__ import annotations

CROP = {
    "wheat": {"hi": "गेहूँ", "mai": "गहूम", "bho": "गेहूँ", "en": "wheat"},
    "maize": {"hi": "मक्का", "mai": "मकई", "bho": "मकई", "en": "maize"},
    "paddy": {"hi": "धान", "mai": "धान", "bho": "धान", "en": "paddy"},
    "potato": {"hi": "आलू", "mai": "अल्लू", "bho": "आलू", "en": "potato"},
    "veg_summer": {"hi": "सब्ज़ी", "mai": "तरकारी", "bho": "तरकारी", "en": "vegetables"},
    "fallow": {"hi": "खाली खेत", "mai": "परती खेत", "bho": "परती खेत", "en": "fallow field"},
}

T: dict[str, dict[str, str]] = {
    "harvest_offer": {
        "hi": "हाँ, हो सकता है। अभी {now} रुपये दें, बाकी {later} रुपये फसल के बाद {due} तक। यह किसान क्रेडिट कार्ड की दर पर है। ठीक है? हाँ के लिए 1, नहीं के लिए 2।",
        "mai": "हँ, भ सकैत अछि। एखन {now} टाका दिअ, बाँकी {later} टाका फसलक बाद {due} धरि। ई किसान क्रेडिट कार्डक दर पर अछि। ठीक? हँ लेल 1, नै लेल 2।",
        "bho": "हँ, हो सकेला। अबहीं {now} रुपया दीं, बाकी {later} रुपया फसल के बाद {due} ले। ई किसान क्रेडिट कार्ड के दर पर बा। ठीक बा? हँ खातिर 1, ना खातिर 2।",
        "en": "Yes. Pay Rs {now} now and Rs {later} after harvest, by {due}. Priced at the Kisan Credit Card rate. OK? Press 1 for yes, 2 for no.",
    },
    "harvest_no": {
        "hi": "माफ़ कीजिए, अभी फसल के बाद भुगतान नहीं हो सकता: {reason}। पूरा {price} रुपये अभी देना होगा।",
        "mai": "माफ करू, एखन फसलक बाद भुगतान नै भ सकैत: {reason}। पूरा {price} टाका एखन देबय पड़त।",
        "bho": "माफ करीं, अबहीं फसल के बाद भुगतान ना हो सकी: {reason}। पूरा {price} रुपया अबहीं देवे के पड़ी।",
        "en": "Sorry, after-harvest payment is not possible now: {reason}. The full Rs {price} is due now.",
    },
    "harvest_done": {
        "hi": "हो गया। {now} रुपये लिए, {later} रुपये {due} तक। कोड {code}।",
        "mai": "भ गेल। {now} टाका लेल, {later} टाका {due} धरि। कोड {code}।",
        "bho": "हो गइल। {now} रुपया लिहल गइल, {later} रुपया {due} ले। कोड {code}।",
        "en": "Done. Rs {now} taken, Rs {later} due by {due}. Code {code}.",
    },
    "advice": {
        "hi": "यह {topic} का सवाल है। सही सलाह के लिए मैंने आपका सवाल भारत-विस्तार को भेज दिया है, संदर्भ {ref}। वहाँ से फ़ोन आएगा, या आप खुद {helpline} पर मुफ़्त कॉल कर सकते हैं। पानी का काम मैं देखूँगा।",
        "mai": "ई {topic} के सवाल अछि। सही सलाह लेल हम अहाँक सवाल भारत-विस्तार के पठा देलहुँ, संदर्भ {ref}। ओतय सँ फोन आएत, वा अहाँ {helpline} पर मुफ्त फोन क सकैत छी। पानिक काज हम देखब।",
        "bho": "ई {topic} के सवाल बा। सही सलाह खातिर हम रउरा सवाल भारत-विस्तार के भेज देनी, संदर्भ {ref}। उहाँ से फोन आई, भा रउआ {helpline} पर मुफत फोन कर सकेनी। पानी के काम हम देखब।",
        "en": "That is a {topic} question. I have sent it to Bharat-VISTAAR for proper advice, reference {ref}. They will call back, or you can call {helpline} free. I will look after the water.",
    },
    "greet": {
        "hi": "नमस्ते {name} जी, मैं सिंचाईस्लॉट साथी बोल रहा हूँ।",
        "mai": "प्रणाम {name} जी, हम सिंचाईस्लॉट साथी बजैत छी।",
        "bho": "प्रणाम {name} जी, हम सिंचाईस्लॉट साथी बोलत बानी।",
        "en": "Hello {name}, this is SinchaiSlot Saathi.",
    },
    "offer": {
        "hi": "आपके {crop} के खेत को आज लगभग {m3} घन मीटर पानी चाहिए। सोलर पंप पर आपका समय {start} से {end} बजे तक हो सकता है। "
              "दाम {price} रुपये, डीज़ल से {saving} रुपये सस्ता। बुक करूँ? हाँ के लिए 1, नहीं के लिए 2 दबाएँ।",
        "mai": "अहाँक {crop} खेत के आइ करीब {m3} घन मीटर पानि चाही। सोलर पंप पर अहाँक समय {start} सँ {end} बजे धरि भ सकैत अछि। "
               "दाम {price} टाका, डीजल सँ {saving} टाका सस्त। बुक करी? हँ लेल 1, नै लेल 2 दबाउ।",
        "bho": "रउरा {crop} के खेत के आज करीब {m3} घन मीटर पानी चाहीं। सोलर पंप पर रउरा समय {start} से {end} बजे ले हो सकेला। "
               "दाम {price} रुपया, डीजल से {saving} रुपया सस्ता। बुक कर दीं? हाँ खातिर 1, ना खातिर 2 दबाईं।",
        "en": "Your {crop} field needs about {m3} cubic metres today. The solar pump can water it from {start} to {end}. "
              "Price Rs {price}, Rs {saving} cheaper than diesel. Shall I book it? Press 1 for yes, 2 for no.",
    },
    "offer_partial": {
        "hi": "आपके {crop} के खेत को लगभग {m3} घन मीटर पानी चाहिए। आज सोलर से {start} से {end} बजे तक लगभग {today} घन मीटर मिलेगा, "
              "बाकी {rest} कल सुबह पहले। कुल दाम {price} रुपये, डीज़ल से {saving} रुपये सस्ता। बुक करूँ? हाँ के लिए 1, नहीं के लिए 2।",
        "mai": "अहाँक {crop} खेत के करीब {m3} घन मीटर पानि चाही। आइ सोलर सँ {start} सँ {end} बजे धरि करीब {today} घन मीटर भेटत, "
               "बाँकी {rest} काल्हि भोरे पहिने। कुल दाम {price} टाका, डीजल सँ {saving} टाका सस्त। बुक करी? हँ लेल 1, नै लेल 2।",
        "bho": "रउरा {crop} के खेत के करीब {m3} घन मीटर पानी चाहीं। आज सोलर से {start} से {end} बजे ले करीब {today} घन मीटर मिली, "
               "बाकी {rest} काल्ह बिहान पहिले। कुल दाम {price} रुपया, डीजल से {saving} रुपया सस्ता। बुक कर दीं? हाँ खातिर 1, ना खातिर 2।",
        "en": "Your {crop} field needs about {m3} cubic metres. Today the solar pump can give about {today} from {start} to {end}, "
              "the remaining {rest} first thing tomorrow. Total Rs {price}, Rs {saving} cheaper than diesel. Book it? 1 yes, 2 no.",
    },
    "booked": {
        "hi": "बुक हो गया। बुकिंग नंबर {booking_id}, समय {start} से {end}, {m3} घन मीटर, {price} रुपये। "
              "पैसा सुनीता दीदी को नकद दें या यूपीआई से भेजें, फिर कोड मिलेगा।",
        "mai": "बुक भ गेल। बुकिंग नम्बर {booking_id}, समय {start} सँ {end}, {m3} घन मीटर, {price} टाका। "
               "पाइ सुनीता दीदी के नगद दिअ वा यूपीआई सँ पठाउ, तखन कोड भेटत।",
        "bho": "बुक हो गइल। बुकिंग नंबर {booking_id}, समय {start} से {end}, {m3} घन मीटर, {price} रुपया। "
               "पइसा सुनीता दीदी के नगद दीं भा यूपीआई से भेजीं, तब कोड मिली।",
        "en": "Booked. Booking {booking_id}, {start} to {end}, {m3} cubic metres, Rs {price}. "
              "Pay Sunita in cash or by UPI and you will get your code.",
    },
    "declined": {
        "hi": "ठीक है, बुकिंग नहीं की। ज़रूरत हो तो फिर से मिस्ड कॉल दें।",
        "mai": "ठीक अछि, बुकिंग नै केलहुँ। काज हो त फेर मिस्ड कॉल दिअ।",
        "bho": "ठीक बा, बुकिंग ना कइनी। जरूरत होखे त फेर मिस्ड कॉल दीं।",
        "en": "Okay, nothing booked. Give a missed call again whenever you need water.",
    },
    "no_sun": {
        "hi": "आज सोलर पंप पर समय नहीं बचा। कल सुबह का समय दूँ, या डीज़ल वाले भाई से अभी पानी चाहिए?",
        "mai": "आइ सोलर पंप पर समय नै बचल। काल्हि भोरक समय दी, वा डीजल वला भाइ सँ एखन पानि चाही?",
        "bho": "आज सोलर पंप पर समय ना बचल। काल्ह बिहान के समय दीं, कि डीजल वाला भाई से अभी पानी चाहीं?",
        "en": "No solar time is left today. Shall I give you tomorrow morning, or do you need diesel water now?",
    },
    "need_met": {
        "hi": "आपके {crop} की मिट्टी में अभी पानी पूरा है, आज सिंचाई की ज़रूरत नहीं है। पानी बचेगा, पैसा भी।",
        "mai": "अहाँक {crop} के माटि मे एखन पानि पूरा अछि, आइ पटवनक जरूरत नै अछि।",
        "bho": "रउरा {crop} के माटी में अभी पानी पूरा बा, आज पटवन के जरूरत नइखे।",
        "en": "Your {crop} field still has enough soil moisture; it does not need water today.",
    },
    "price": {
        "hi": "सोलर पानी {tariff} रुपये प्रति घन मीटर है। {m3} घन मीटर का {price} रुपये, डीज़ल से लगभग {diesel} रुपये लगते।",
        "mai": "सोलर पानि {tariff} टाका प्रति घन मीटर अछि। {m3} घन मीटरक {price} टाका, डीजल सँ करीब {diesel} टाका लगितय।",
        "bho": "सोलर पानी {tariff} रुपया प्रति घन मीटर बा। {m3} घन मीटर के {price} रुपया, डीजल से करीब {diesel} रुपया लागित।",
        "en": "Solar water is Rs {tariff} per cubic metre. {m3} cubic metres costs Rs {price}; diesel would be about Rs {diesel}.",
    },
    "balance": {
        "hi": "आपका बकाया {due} रुपये है और जमा {credit} रुपये।",
        "mai": "अहाँक बकाया {due} टाका अछि आ जमा {credit} टाका।",
        "bho": "रउरा बकाया {due} रुपया बा आ जमा {credit} रुपया।",
        "en": "You owe Rs {due} and have Rs {credit} credit.",
    },
    "cancel_confirm": {
        "hi": "बुकिंग {booking_id} रद्द करूँ? हाँ के लिए 1, नहीं के लिए 2।",
        "mai": "बुकिंग {booking_id} रद्द करी? हँ लेल 1, नै लेल 2।",
        "bho": "बुकिंग {booking_id} रद्द कर दीं? हाँ खातिर 1, ना खातिर 2।",
        "en": "Cancel booking {booking_id}? Press 1 for yes, 2 for no.",
    },
    "cancelled": {
        "hi": "बुकिंग {booking_id} रद्द हो गई। {refund} रुपये आपके खाते में जमा।",
        "mai": "बुकिंग {booking_id} रद्द भ गेल। {refund} टाका अहाँक खाता मे जमा।",
        "bho": "बुकिंग {booking_id} रद्द हो गइल। {refund} रुपया रउरा खाता में जमा।",
        "en": "Booking {booking_id} cancelled. Rs {refund} credited to your account.",
    },
    "issue": {
        "hi": "शिकायत दर्ज हो गई, नंबर {issue_id}। सुनीता दीदी जल्दी देखेंगी।",
        "mai": "शिकायत दर्ज भ गेल, नम्बर {issue_id}। सुनीता दीदी जल्दी देखती।",
        "bho": "शिकायत दर्ज हो गइल, नंबर {issue_id}। सुनीता दीदी जल्दी देखिहें।",
        "en": "Complaint logged, number {issue_id}. Sunita will look at it soon.",
    },
    "schemes": {
        "hi": "आपके लिए: {list}। पूरी जानकारी कृषि कार्यालय से पक्की कर लें।",
        "mai": "अहाँ लेल: {list}। पूरा जानकारी कृषि कार्यालय सँ पक्का क लिअ।",
        "bho": "रउरा खातिर: {list}। पूरा जानकारी कृषि दफ्तर से पक्का कर लीं।",
        "en": "For you: {list}. Please confirm the details with the agriculture office.",
    },
    "status": {
        "hi": "आपकी बुकिंग: {list}।", "mai": "अहाँक बुकिंग: {list}।", "bho": "रउरा बुकिंग: {list}।",
        "en": "Your bookings: {list}.",
    },
    "no_bookings": {
        "hi": "आपकी कोई बुकिंग नहीं है।", "mai": "अहाँक कोनो बुकिंग नै अछि।", "bho": "रउरा कवनो बुकिंग नइखे।",
        "en": "You have no bookings.",
    },
    "pay": {
        "hi": "बुकिंग {booking_id} के {amount} रुपये यूपीआई से भेजें। लिंक एसएमएस पर भेज दिया है (टेस्ट मोड)।",
        "mai": "बुकिंग {booking_id} के {amount} टाका यूपीआई सँ पठाउ। लिंक एसएमएस पर पठा देल (टेस्ट मोड)।",
        "bho": "बुकिंग {booking_id} के {amount} रुपया यूपीआई से भेजीं। लिंक एसएमएस पर भेज देले बानी (टेस्ट मोड)।",
        "en": "Send Rs {amount} for booking {booking_id} by UPI. The link is on SMS (test mode).",
    },
    "why": {
        "hi": "{at} बजे बादल का अनुमान आया, इसलिए आपका समय {old} से {new} किया गया। पानी उतना ही मिलेगा।",
        "mai": "{at} बजे मेघक अनुमान आयल, तैं अहाँक समय {old} सँ {new} कएल गेल। पानि ओतबे भेटत।",
        "bho": "{at} बजे बादर के अनुमान आइल, एही से रउरा समय {old} से {new} कइल गइल। पानी ओतने मिली।",
        "en": "At {at} the forecast showed cloud, so your time moved from {old} to {new}. You still get the same water.",
    },
    "why_none": {
        "hi": "आपके समय में कोई बदलाव नहीं हुआ है।", "mai": "अहाँक समय मे कोनो बदलाव नै भेल अछि।",
        "bho": "रउरा समय में कवनो बदलाव नइखे भइल।", "en": "Your time has not changed.",
    },
    "diesel": {
        "hi": "पास के पंप: {list}। सोलर भर जाए तो इनसे पानी ले सकते हैं।",
        "mai": "लगक पंप: {list}। सोलर भरि जाए त हिनका सँ पानि ल सकैत छी।",
        "bho": "लगे के पंप: {list}। सोलर भर जाव त इनहन से पानी ले सकेनी।",
        "en": "Nearby pumps: {list}. Use them when the solar pump is full.",
    },
    "help": {
        "hi": "आप कह सकते हैं: पानी चाहिए, कितना लगेगा, मेरी बुकिंग, रद्द करो, या शिकायत।",
        "mai": "अहाँ कहि सकैत छी: पानि चाही, कतेक लागत, हमर बुकिंग, रद्द करू, वा शिकायत।",
        "bho": "रउआ कह सकेनी: पानी चाहीं, केतना लागी, हमार बुकिंग, रद्द करीं, भा शिकायत।",
        "en": "You can say: I need water, how much, my booking, cancel, or complaint.",
    },
    "escalate": {
        "hi": "माफ़ कीजिए, मैं समझ नहीं पाया। सुनीता दीदी आपको वापस फ़ोन करेंगी।",
        "mai": "माफ करू, हम नै बुझलहुँ। सुनीता दीदी अहाँ के फेर फोन करती।",
        "bho": "माफ करीं, हम ना समझनी। सुनीता दीदी रउआ के फेर फोन करिहें।",
        "en": "Sorry, I did not understand. Sunita will call you back.",
    },
    "callback_moved": {
        "hi": "नमस्ते {name} जी। बादल की वजह से आपका पानी का समय {old} से बदलकर {new} बजे कर दिया गया है। पानी उतना ही मिलेगा।",
        "mai": "प्रणाम {name} जी। मेघक कारण अहाँक पानिक समय {old} सँ बदलि क {new} बजे कएल गेल अछि। पानि ओतबे भेटत।",
        "bho": "प्रणाम {name} जी। बादर के चलते रउरा पानी के समय {old} से बदल के {new} बजे कइल गइल बा। पानी ओतने मिली।",
        "en": "Hello {name}. Because of cloud, your water time moved from {old} to {new}. You still get the same water.",
    },
    "callback_moved_partial": {
        "hi": "नमस्ते {name} जी। बादल की वजह से धूप कम है। आपका पानी अब {new} बजे, आज लगभग {today} घन मीटर मिलेगा, बाकी {rest} कल सुबह पहले नंबर पर।",
        "mai": "प्रणाम {name} जी। मेघक कारण रौद कम अछि। अहाँक पानि आब {new} बजे, आइ करीब {today} घन मीटर भेटत, बाँकी {rest} काल्हि भोरे पहिल नम्बर पर।",
        "bho": "प्रणाम {name} जी। बादर के चलते घाम कम बा। रउरा पानी अब {new} बजे, आज करीब {today} घन मीटर मिली, बाकी {rest} काल्ह बिहान पहिला नंबर पर।",
        "en": "Hello {name}. Cloud has cut the sun. Your water is now {new}: about {today} cubic metres today, the remaining {rest} first thing tomorrow.",
    },
    "callback_dropped": {
        "hi": "नमस्ते {name} जी। बादल की वजह से आज {old} बजे का समय नहीं हो पाएगा। आपकी बुकिंग कल सुबह पहले नंबर पर है।",
        "mai": "प्रणाम {name} जी। मेघक कारण आइ {old} बजे वला समय नै भ पाओत। अहाँक बुकिंग काल्हि भोरे पहिल नम्बर पर अछि।",
        "bho": "प्रणाम {name} जी। बादर के चलते आज {old} बजे वाला समय ना हो पाई। रउरा बुकिंग काल्ह बिहान पहिला नंबर पर बा।",
        "en": "Hello {name}. Because of cloud the {old} slot cannot run today. Your booking is first in line tomorrow morning.",
    },
    "callback_added": {
        "hi": "नमस्ते {name} जी। आपका पानी का समय {new} बजे तय हुआ है।",
        "mai": "प्रणाम {name} जी। अहाँक पानिक समय {new} बजे तय भेल अछि।",
        "bho": "प्रणाम {name} जी। रउरा पानी के समय {new} बजे तय भइल बा।",
        "en": "Hello {name}. Your water time is set for {new}.",
    },
}


def say(key: str, lang: str, **kw) -> str:
    table = T[key]
    return table.get(lang, table["hi"]).format(**kw)


def crop_name(key: str, lang: str) -> str:
    return CROP.get(key, {}).get(lang, key)
