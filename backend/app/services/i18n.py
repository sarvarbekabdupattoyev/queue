"""Bot-facing translations (uz / ru / en).

The client picks a language on first /start (stored per company+chat in
``bot_users``); every bot message and queue notification is rendered through
:func:`t`. Staff dashboards and API errors stay Uzbek — this table is only
for what clients see inside Telegram.
"""

from app.models.enums import TicketStatus

LANGS = ("uz", "ru", "en")
DEFAULT_LANG = "uz"


def norm_lang(lang: str | None) -> str:
    return lang if lang in LANGS else DEFAULT_LANG


def t(lang: str | None, key: str, **kwargs: object) -> str:
    text = _T[key][norm_lang(lang)]
    return text.format(**kwargs) if kwargs else text


def status_label(lang: str | None, status: TicketStatus) -> str:
    return _STATUS[status][norm_lang(lang)]


# shown before any language is known, so it speaks all three at once
LANGUAGE_PROMPT = "Tilni tanlang · Выберите язык · Choose a language:"

LANGUAGE_NAMES = {"uz": "🇺🇿 O'zbek", "ru": "🇷🇺 Русский", "en": "🇬🇧 English"}

_STATUS: dict[TicketStatus, dict[str, str]] = {
    TicketStatus.REGISTERED: {
        "uz": "Ro'yxatdan o'tgan (hali kelmagan)",
        "ru": "Зарегистрирован (ещё не пришёл)",
        "en": "Registered (not arrived yet)",
    },
    TicketStatus.CHECKED_IN: {
        "uz": "Keldi — navbat kutmoqda",
        "ru": "Пришёл — ожидает очереди",
        "en": "Arrived — waiting in the queue",
    },
    TicketStatus.CALLED: {"uz": "Chaqirildi", "ru": "Вызван", "en": "Called"},
    TicketStatus.SERVING: {
        "uz": "Xizmat ko'rsatilmoqda",
        "ru": "Обслуживается",
        "en": "Being served",
    },
    TicketStatus.DONE: {"uz": "Yakunlandi", "ru": "Завершено", "en": "Finished"},
    TicketStatus.SKIPPED: {
        "uz": "O'tkazib yuborilgan (kelmadi)",
        "ru": "Пропущен (не подошёл)",
        "en": "Skipped (did not show up)",
    },
    TicketStatus.CANCELLED: {"uz": "Bekor qilingan", "ru": "Отменён", "en": "Cancelled"},
}

_T: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------ menu/UI ---
    "btn_ticket": {"uz": "🎫 Mening navbatim", "ru": "🎫 Моя очередь", "en": "🎫 My ticket"},
    "btn_status": {"uz": "📊 Navbat holati", "ru": "📊 Статус очереди", "en": "📊 Queue status"},
    "btn_info": {"uz": "ℹ️ Ma'lumot", "ru": "ℹ️ Информация", "en": "ℹ️ Information"},
    "btn_language": {"uz": "🌐 Til", "ru": "🌐 Язык", "en": "🌐 Language"},
    "btn_share_phone": {
        "uz": "📱 Raqamni yuborish",
        "ru": "📱 Отправить номер",
        "en": "📱 Share my number",
    },
    "language_saved": {
        "uz": "✅ Til saqlandi: O'zbek",
        "ru": "✅ Язык сохранён: Русский",
        "en": "✅ Language saved: English",
    },
    "cmd_start_desc": {
        "uz": "Ro'yxatdan o'tish",
        "ru": "Регистрация",
        "en": "Register",
    },
    "cmd_ticket_desc": {
        "uz": "Mening navbatim (QR-kod)",
        "ru": "Моя очередь (QR-код)",
        "en": "My ticket (QR code)",
    },
    "cmd_status_desc": {
        "uz": "Navbat holati",
        "ru": "Статус очереди",
        "en": "Queue status",
    },
    "cmd_info_desc": {
        "uz": "Kompaniya haqida ma'lumot",
        "ru": "Информация о компании",
        "en": "Company information",
    },
    "help_text": {
        "uz": "/start — ro'yxatdan o'tish\n/navbat — mening navbatim (QR-kod)\n"
              "/holat — navbat holati\n/info — kompaniya haqida ma'lumot",
        "ru": "/start — регистрация\n/navbat — моя очередь (QR-код)\n"
              "/holat — статус очереди\n/info — информация о компании",
        "en": "/start — register\n/navbat — my ticket (QR code)\n"
              "/holat — queue status\n/info — company information",
    },
    # -------------------------------------------------------- start / flow ---
    "already_have_tickets": {
        "uz": "Siz allaqachon ro'yxatdan o'tgansiz. Mana navbatingiz:",
        "ru": "Вы уже зарегистрированы. Вот ваша очередь:",
        "en": "You are already registered. Here is your ticket:",
    },
    "no_open_events": {
        "uz": "Hozircha ochiq tadbirlar yo'q. Tadbir e'lon qilinganda qayta urinib ko'ring.",
        "ru": "Открытых мероприятий пока нет. Попробуйте снова, когда объявят продажу.",
        "en": "There are no open events yet. Please try again when a sale is announced.",
    },
    "welcome_single_event": {
        "uz": "Assalomu alaykum! «{event}» uchun onlayn navbat botiga xush kelibsiz.\n\n"
              "Ro'yxatdan o'tish uchun 2 ta qadam bor: F.I.Sh. va telefon raqam. "
              "Bitta telefon raqamiga bitta navbat beriladi.",
        "ru": "Здравствуйте! Это бот онлайн-очереди «{event}».\n\n"
              "Регистрация в 2 шага: Ф.И.О. и номер телефона. "
              "На один номер телефона выдаётся одна очередь.",
        "en": "Hello! Welcome to the online queue bot for “{event}”.\n\n"
              "Registration takes 2 steps: your full name and phone number. "
              "One phone number gets one ticket.",
    },
    "choose_event": {
        "uz": "Assalomu alaykum! Qaysi tadbir uchun navbat olasiz?",
        "ru": "Здравствуйте! На какое мероприятие вы хотите занять очередь?",
        "en": "Hello! Which event would you like to queue for?",
    },
    "event_closed_alert": {
        "uz": "Bu tadbir uchun ro'yxat yopilgan",
        "ru": "Регистрация на это мероприятие закрыта",
        "en": "Registration for this event is closed",
    },
    "choose_branch": {
        "uz": "Tadbir bir nechta filialda o'tkaziladi. Qaysi filialga borasiz? "
              "Navbatingiz shu filialda amal qiladi.",
        "ru": "Мероприятие проходит в нескольких филиалах. В какой филиал вы придёте? "
              "Ваша очередь будет действовать именно там.",
        "en": "This event runs in several branches. Which branch will you visit? "
              "Your ticket will be valid at that branch.",
    },
    "branch_closed_alert": {
        "uz": "Bu filial uchun ro'yxatdan o'tib bo'lmaydi",
        "ru": "Регистрация в этот филиал недоступна",
        "en": "Registration for this branch is not available",
    },
    "branch_line": {"uz": "📍 Filial: {branch}", "ru": "📍 Филиал: {branch}", "en": "📍 Branch: {branch}"},
    "ask_fio": {
        "uz": "1/2 — F.I.Sh. ni bir qatorda yozing (Ism Familiya Otasining ismi).\n"
              "Masalan: Sardor Rahimov Akmal o'g'li",
        "ru": "1/2 — Напишите Ф.И.О. одной строкой (Имя Фамилия Отчество).\n"
              "Например: Сардор Рахимов Акмал угли",
        "en": "1/2 — Send your full name in one line (First name, Last name, Patronymic).\n"
              "For example: Sardor Rahimov Akmal ogli",
    },
    "fio_invalid": {
        "uz": "Iltimos, F.I.Sh. ni faqat harflardan iborat 2–5 ta so'z bilan bir qatorda yozing "
              "(masalan: Sardor Rahimov Akmal o'g'li).",
        "ru": "Пожалуйста, напишите Ф.И.О. одной строкой: 2–5 слов, только буквы "
              "(например: Сардор Рахимов Акмал угли).",
        "en": "Please send your full name in one line: 2–5 words, letters only "
              "(for example: Sardor Rahimov Akmal ogli).",
    },
    "ask_phone": {
        "uz": "2/2 — Telefon raqamingizni pastdagi «📱 Raqamni yuborish» tugmasi orqali ulashing. "
              "Raqamni qo'lda yozib bo'lmaydi — faqat tugma orqali qabul qilinadi.",
        "ru": "2/2 — Отправьте свой номер телефона кнопкой «📱 Отправить номер» ниже. "
              "Ввести номер вручную нельзя — принимается только через кнопку.",
        "en": "2/2 — Share your phone number using the “📱 Share my number” button below. "
              "Typing the number is not allowed — it is accepted only via the button.",
    },
    "phone_only_button": {
        "uz": "☝️ Raqam qo'lda qabul qilinmaydi. Iltimos, pastdagi «📱 Raqamni yuborish» "
              "tugmasini bosing.",
        "ru": "☝️ Номер, набранный вручную, не принимается. Пожалуйста, нажмите кнопку "
              "«📱 Отправить номер» ниже.",
        "en": "☝️ Typed numbers are not accepted. Please tap the “📱 Share my number” "
              "button below.",
    },
    "phone_not_yours": {
        "uz": "Bu kontakt sizniki emas. Iltimos, tugma orqali o'zingizning raqamingizni yuboring.",
        "ru": "Этот контакт не ваш. Пожалуйста, отправьте свой собственный номер через кнопку.",
        "en": "That contact is not yours. Please share your own number using the button.",
    },
    "phone_invalid": {
        "uz": "Afsuski, faqat O'zbekiston raqamlari (+998) qabul qilinadi.",
        "ru": "К сожалению, принимаются только узбекские номера (+998).",
        "en": "Sorry, only Uzbekistan phone numbers (+998) are accepted.",
    },
    "phone_taken": {
        "uz": "Bu telefon raqamiga navbat allaqachon berilgan. Mana u:",
        "ru": "На этот номер телефона очередь уже выдана. Вот она:",
        "en": "A ticket has already been issued for this phone number. Here it is:",
    },
    "registration_closed": {
        "uz": "Afsuski, bu tadbir uchun ro'yxat yopildi.",
        "ru": "К сожалению, регистрация на это мероприятие закрылась.",
        "en": "Unfortunately, registration for this event has closed.",
    },
    "registered_ok": {"uz": "✅ Ro'yxatdan o'tdingiz!", "ru": "✅ Вы зарегистрированы!", "en": "✅ You are registered!"},
    "registered_ok_late": {
        "uz": "✅ Ro'yxatga olindingiz! Asosiy ro'yxat davri tugagani uchun QR skanerlangach "
              "kun oxiri (oxirgi) navbatga qo'shilasiz.",
        "ru": "✅ Вы зарегистрированы! Основной период регистрации завершился, поэтому после "
              "сканирования QR вы попадёте в очередь конца дня.",
        "en": "✅ You are registered! The main registration period is over, so after your QR "
              "is scanned you will join the end-of-day queue.",
    },
    "not_registered_yet": {
        "uz": "Siz hali ro'yxatdan o'tmagansiz. /start ni bosing.",
        "ru": "Вы ещё не зарегистрированы. Нажмите /start.",
        "en": "You are not registered yet. Press /start.",
    },
    "start_over": {
        "uz": "Ro'yxatdan o'tish uchun /start ni bosing.",
        "ru": "Чтобы зарегистрироваться, нажмите /start.",
        "en": "Press /start to register.",
    },
    # ------------------------------------------------------------- ticket ---
    # the code stands alone on an emphasized line (and is also drawn in large
    # type inside the QR photo itself); reg_time carries milliseconds because
    # the registration moment IS the queue order
    "ticket_caption": {
        "uz": "{intro}🎫 Navbat kodingiz:\n\n▶️ №{number} ◀️\n\n🗓 {event} — {starts}\n{branch_line}"
              "👤 {name}\n📞 {phone}\n"
              "🕐 Ro'yxatdan o'tgan vaqtingiz: {reg_time}\n\n"
              "Ofisga kelganda shu QR-kodni qabulxonada ko'rsating — kelganingiz qayd etiladi. "
              "Skanerlash {deadline} gacha. Navbat tartibi ro'yxatdan o'tgan vaqtingiz "
              "bo'yicha belgilanadi.\n\nHolat: {status}",
        "ru": "{intro}🎫 Ваш код очереди:\n\n▶️ №{number} ◀️\n\n🗓 {event} — {starts}\n{branch_line}"
              "👤 {name}\n📞 {phone}\n"
              "🕐 Время вашей регистрации: {reg_time}\n\n"
              "Придя в офис, покажите этот QR-код на ресепшене — вашу явку отметят. "
              "Сканирование до {deadline}. Порядок очереди определяется временем "
              "вашей регистрации.\n\nСтатус: {status}",
        "en": "{intro}🎫 Your queue code:\n\n▶️ №{number} ◀️\n\n🗓 {event} — {starts}\n{branch_line}"
              "👤 {name}\n📞 {phone}\n"
              "🕐 Your registration time: {reg_time}\n\n"
              "When you arrive, show this QR code at the reception desk to check in. "
              "Scanning is open until {deadline}. The queue order is based on your "
              "registration time.\n\nStatus: {status}",
    },
    # ------------------------------------------------------------- status ---
    "now_serving": {
        "uz": "Hozir {list} qabul qilinmoqda.",
        "ru": "Сейчас обслуживаются: {list}.",
        "en": "Now serving: {list}.",
    },
    "nobody_called": {
        "uz": "Hozircha hech kim chaqirilmagan.",
        "ru": "Пока никто не вызван.",
        "en": "Nobody has been called yet.",
    },
    "desk_short": {"uz": "{desk}-stol", "ru": "стол {desk}", "en": "desk {desk}"},
    "status_summary": {
        "uz": "📊 {now_line} Kutayotganlar: {waiting} kishi.\n\n{mine}",
        "ru": "📊 {now_line} Ожидают: {waiting} чел.\n\n{mine}",
        "en": "📊 {now_line} Waiting: {waiting} people.\n\n{mine}",
    },
    "your_pos_queue": {
        "uz": "Sizning kodingiz: №{number}. Sizdan oldin {ahead} kishi bor.",
        "ru": "Ваш код: №{number}. Перед вами {ahead} человек.",
        "en": "Your code: №{number}. There are {ahead} people ahead of you.",
    },
    "your_pos_prequeue": {
        "uz": "Sizning kodingiz: №{number}. Kelganingiz qayd etilgan. Sotuv {time} da "
              "boshlanadi — navbat tartibi shu paytda yuboriladi.",
        "ru": "Ваш код: №{number}. Ваша явка отмечена. Продажа начнётся в {time} — "
              "порядок очереди придёт в этот момент.",
        "en": "Your code: №{number}. Your arrival is recorded. The sale starts at {time} — "
              "your place in the queue will be sent then.",
    },
    "your_called": {
        "uz": "Sizning kodingiz: №{number} — chaqirilgansiz! {desk}-stolga yaqinlashing.",
        "ru": "Ваш код: №{number} — вас вызвали! Подойдите к столу {desk}.",
        "en": "Your code: №{number} — you have been called! Please go to desk {desk}.",
    },
    "your_registered": {
        "uz": "Sizning kodingiz: №{number}. Ofisga kelganda QR-kodni qabulxonada "
              "ko'rsating ({deadline} gacha).",
        "ru": "Ваш код: №{number}. Придя в офис, покажите QR-код на ресепшене "
              "(до {deadline}).",
        "en": "Your code: №{number}. When you arrive, show your QR code at the "
              "reception desk (until {deadline}).",
    },
    "your_status": {
        "uz": "Sizning kodingiz: №{number}. Holat: {status}.",
        "ru": "Ваш код: №{number}. Статус: {status}.",
        "en": "Your code: №{number}. Status: {status}.",
    },
    # ---------------------------------------------------------- company info ---
    "info_events_header": {
        "uz": "🗓 Yaqin sotuv tadbirlari",
        "ru": "🗓 Ближайшие продажи",
        "en": "🗓 Upcoming sale events",
    },
    "info_event_line": {
        "uz": "• {name} — boshlanishi {starts}, skanerlash {deadline} gacha",
        "ru": "• {name} — начало {starts}, сканирование до {deadline}",
        "en": "• {name} — starts {starts}, scanning until {deadline}",
    },
    "info_locations_header": {"uz": "📍 Manzillar", "ru": "📍 Адреса", "en": "📍 Locations"},
    "info_phones_header": {
        "uz": "📞 Aloqa raqamlari",
        "ru": "📞 Контактные телефоны",
        "en": "📞 Contact numbers",
    },
    "info_map_link": {"uz": "xarita", "ru": "карта", "en": "map"},
    "info_no_details": {
        "uz": "Qo'shimcha ma'lumotlar hozircha kiritilmagan.",
        "ru": "Дополнительная информация пока не добавлена.",
        "en": "No additional details have been added yet.",
    },
    # ------------------------------------------------- queue notifications ---
    "ntf_checkin_prequeue": {
        "uz": "✅ Kelganingiz qayd etildi (№{number}).\nSotuv {time} da boshlanadi. Navbat "
              "tartibi botdan ro'yxatdan o'tgan vaqt bo'yicha belgilanadi va sotuv "
              "boshlanganda shu yerda yuboriladi.",
        "ru": "✅ Ваша явка отмечена (№{number}).\nПродажа начнётся в {time}. Порядок — по "
              "времени регистрации в боте; ваш номер в очереди придёт сюда, когда "
              "продажа начнётся.",
        "en": "✅ Your arrival has been recorded (№{number}).\nThe sale starts at {time}. "
              "The order follows bot registration time — your place in the queue will be "
              "sent here when the sale starts.",
    },
    "ntf_checkin_late_prequeue": {
        "uz": "✅ Qayd etildi (№{number}). Siz kun oxiri (oxirgi) navbatga qo'shildingiz. "
              "Sotuv {time} da boshlanadi — tartibingiz keyin xabar qilinadi.",
        "ru": "✅ Отмечено (№{number}). Вы добавлены в очередь конца дня. Продажа начнётся "
              "в {time} — ваш порядок сообщим позже.",
        "en": "✅ Recorded (№{number}). You joined the end-of-day queue. The sale starts at "
              "{time} — your place will be announced later.",
    },
    "ntf_sale_started": {
        "uz": "🔥 Sotuv boshlandi!\nSizning kodingiz: №{number}\nBotda ro'yxatdan o'tgan "
              "vaqtingiz: {reg_time}\nSizdan oldin {ahead} kishi bor. Chaqirilganingizda "
              "xabar keladi.",
        "ru": "🔥 Продажа началась!\nВаш код: №{number}\nВремя вашей регистрации в боте: "
              "{reg_time}\nПеред вами {ahead} человек. Когда вас вызовут, придёт сообщение.",
        "en": "🔥 The sale has started!\nYour code: №{number}\nYour bot registration time: "
              "{reg_time}\nThere are {ahead} people ahead of you. You will get a message "
              "when you are called.",
    },
    "ntf_checkin_late": {
        "uz": "✅ Qayd etildi (№{number}). Skanerlash vaqti tugagani uchun kun oxiri "
              "navbatiga qo'shildingiz — sizdan oldin {ahead} kishi bor.",
        "ru": "✅ Отмечено (№{number}). Время сканирования истекло, поэтому вы добавлены в "
              "очередь конца дня — перед вами {ahead} человек.",
        "en": "✅ Recorded (№{number}). Scanning time is over, so you joined the end-of-day "
              "queue — there are {ahead} people ahead of you.",
    },
    "ntf_cancelled_two_skips": {
        "uz": "Navbatingiz (№{number}) bekor qilindi: ikki marta chaqiruvda bo'lmadingiz.",
        "ru": "Ваша очередь (№{number}) отменена: вы дважды не подошли по вызову.",
        "en": "Your ticket (№{number}) has been cancelled: you missed the call twice.",
    },
    "ntf_rejoined_late": {
        "uz": "↩️ Kun oxiri navbatiga qo'shildingiz (№{number}). Sizdan oldin {ahead} kishi bor.",
        "ru": "↩️ Вы добавлены в очередь конца дня (№{number}). Перед вами {ahead} человек.",
        "en": "↩️ You have joined the end-of-day queue (№{number}). There are {ahead} people "
              "ahead of you.",
    },
    "ntf_called": {
        "uz": "🔔 Sizning navbatingiz! №{number} — {desk}-stolga yaqinlashing.\n{minutes} "
              "daqiqa ichida kelmasangiz o'tkazib yuborilasiz.",
        "ru": "🔔 Ваша очередь! №{number} — подойдите к столу {desk}.\nЕсли не подойдёте за "
              "{minutes} минут(ы), вас пропустят.",
        "en": "🔔 It's your turn! №{number} — please go to desk {desk}.\nIf you don't come "
              "within {minutes} minutes, you will be skipped.",
    },
    "ntf_recalled": {
        "uz": "🔔🔔 Takroriy chaqiruv: №{number} — {desk}-stolga yaqinlashing!",
        "ru": "🔔🔔 Повторный вызов: №{number} — подойдите к столу {desk}!",
        "en": "🔔🔔 Repeated call: №{number} — please go to desk {desk}!",
    },
    "ntf_skip_final": {
        "uz": "⏭ Chaqiruvda yana bo'lmadingiz. Kun oxiri navbati faqat bir marta beriladi — "
              "qabulxonaga murojaat qiling.",
        "ru": "⏭ Вы снова не подошли по вызову. Очередь конца дня даётся только один раз — "
              "обратитесь на ресепшен.",
        "en": "⏭ You missed the call again. The end-of-day queue is given only once — "
              "please contact the reception desk.",
    },
    "ntf_skip_once": {
        "uz": "⏭ Afsuski, chaqiruvda bo'lmadingiz va o'tkazib yuborildingiz. Ofisda "
              "bo'lsangiz, qabulxonada QR-kodingizni qayta ko'rsating — kun oxiri "
              "navbatiga qo'shamiz (bir marta).",
        "ru": "⏭ К сожалению, вы не подошли по вызову и были пропущены. Если вы в офисе, "
              "снова покажите QR-код на ресепшене — добавим вас в очередь конца дня "
              "(один раз).",
        "en": "⏭ Unfortunately, you missed the call and were skipped. If you are at the "
              "office, show your QR code at the reception desk again — we will add you to "
              "the end-of-day queue (once).",
    },
    "ntf_done": {
        "uz": "🎉 Rahmat! Xizmat yakunlandi (№{number}). Yaxshi kun tilaymiz.",
        "ru": "🎉 Спасибо! Обслуживание завершено (№{number}). Хорошего дня!",
        "en": "🎉 Thank you! Your service is complete (№{number}). Have a great day!",
    },
    "ntf_cancelled_admin": {
        "uz": "Navbatingiz (№{number}) administrator tomonidan bekor qilindi.",
        "ru": "Ваша очередь (№{number}) отменена администратором.",
        "en": "Your ticket (№{number}) has been cancelled by an administrator.",
    },
}
