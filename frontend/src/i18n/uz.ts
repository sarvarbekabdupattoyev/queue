export const uz = {
  langName: 'O‘zbekcha',
  nav: {
    how: 'Qanday ishlaydi',
    features: 'Imkoniyatlar',
    faq: 'Savollar',
    login: 'Kirish',
    start: 'Bepul boshlash',
    dashboard: 'Boshqaruv paneli',
  },
  hero: {
    badge: 'Telegram-bot · QR · jonli navbat',
    title1: 'Sotuv kunlari uchun',
    titleAccent: 'adolatli navbat',
    title2: 'tizimi',
    sub: 'Mijozlar Telegram-botda ro‘yxatdan o‘tib, tasodifiy 4 harfli kod va QR-kod oladi. Sotuv kuni QR skanerlanadi, belgilangan vaqtdan so‘ng navbat — faqat kelganlar orasida, botdagi ro‘yxat vaqti bo‘yicha boshlanadi.',
    ctaPrimary: 'Bepul boshlash',
    ctaSecondary: 'Qanday ishlaydi?',
    note: 'Mijozlarga ilova kerak emas — faqat Telegram',
  },
  board: {
    live: 'JONLI',
    calling: 'Hozir chaqirilmoqda',
    desk: '{n}-stol',
    next: 'Keyingi navbat',
    ticket: 'Sizning kodingiz',
    scanUntil: 'Skanerlash 10:00 gacha',
    botChip: 'Telegram-bot',
  },
  audience: {
    title: 'Kimlar uchun',
    items: ['Uy-joy sotuvlari', 'Avtosalonlar', 'Banklar', 'Klinikalar', 'Ta’lim markazlari', 'Tadbirlar', 'Davlat xizmatlari'],
  },
  how: {
    title: 'Qanday ishlaydi',
    sub: 'To‘rt bosqich — ro‘yxatdan yakuniy xizmatgacha. Hammasi avtomatik.',
    steps: [
      {
        title: 'Botda ro‘yxat',
        text: 'Mijoz kompaniyangiz Telegram-botiga /start yozadi: ism, familiya, telefon. Bot unga tasodifiy 4 harfli kod va QR-kod beradi — tartib bilan emas, taxmin qilib bo‘lmaydi.',
      },
      {
        title: 'Sotuv kuni — QR skaner',
        text: 'Mijoz ofisga kelib QR-kodini qabulxonada skanerlatadi (USB skaner, kamera yoki kodni qo‘lda kiritish). Siz belgilagan muddatgacha skanerlash davom etadi.',
      },
      {
        title: 'Vaqt tugadi — navbat boshlanadi',
        text: 'Belgilangan vaqt kelganda navbat avtomatik shakllanadi: faqat skanerdan o‘tganlar, botdagi ro‘yxat vaqti bo‘yicha. Kim oldin yozilgan bo‘lsa — o‘sha oldinda. Kechikkanlar kun oxiriga qo‘shiladi.',
      },
      {
        title: 'Chaqiruv va xizmat',
        text: 'Menejerlar o‘z stolidan «Keyingini chaqirish»ni bosadi. Kod katta ekranda chiqadi, mijozga Telegramdan xabar boradi. Kelmaganlar bir marta kun oxiriga o‘tadi, ikkinchisida bekor bo‘ladi.',
      },
    ],
  },
  fair: {
    title: 'Tartib — ro‘yxat vaqti bo‘yicha. Kelish tartibi emas.',
    sub: 'Tungi navbatlar va tirbandlik tugaydi: ertalab kim birinchi kelgani emas, botda kim birinchi yozilgani muhim. Skanerlanmaganlar navbatga kirmaydi.',
    phases: ['1 · Botda ro‘yxat', '2 · Ofisga kelish', '3 · Yakuniy navbat'],
    registered: 'yozildi',
    arrived: 'keldi',
    notScanned: 'skanerlanmadi — navbatdan chetda',
    queuePos: '-o‘rin',
  },
  features: {
    title: 'Sotuv kuni uchun to‘liq to‘plam',
    sub: 'Ro‘yxatdan katta ekrangacha — bitta tizim, ortiqcha narsa yo‘q.',
    items: [
      {
        title: 'Har kompaniyaga o‘z boti',
        text: 'BotFather’dan token olasiz, tizimga qo‘yasiz — bot darhol ishga tushadi. Ro‘yxat, QR-kod, holat va chaqiruv xabarlari — hammasi sizning bot nomingizdan.',
      },
      {
        title: 'QR skaner — 3 usul',
        text: 'USB skaner (klaviatura kabi), telefon/noutbuk kamerasi yoki 4 harfli kodni qo‘lda kiritish. Natija rangli va aniq: qabul, kun oxiri yoki xato.',
      },
      {
        title: 'Katta ekran (TV tablo)',
        text: 'Chaqirilgan kodlar, mijoz ismlari, stollar, taymer va botdagi ro‘yxat vaqtlari bilan keyingi navbat — jonli. Havolani televizordagi brauzerga ochasiz, xolos. Ovozli signal ham bor.',
      },
      {
        title: 'Menejer paneli',
        text: 'Chaqirish · Keldi · Kelmadi · Yakunlash — planshetga mos yirik tugmalar, chaqiruv taymeri, boshqa stollar holati va jonli navbat ro‘yxati.',
      },
      {
        title: 'Rollar va xavfsizlik',
        text: 'Egasi, menejer, QR-skaner rollari. Xodim parollari tizim tomonidan yaratiladi va bir marta ko‘rsatiladi. Har bir kompaniya ma’lumoti qat’iy ajratilgan.',
      },
      {
        title: 'Katta oqimga chidamli',
        text: 'Bir necha daqiqada 2 000+ ro‘yxatni qabul qiladi, ekranlar WebSocket orqali soniyada yangilanadi, aloqa uzilsa o‘zi tiklanadi.',
      },
    ],
  },
  stats: [
    { value: 2000, prefix: '', suffix: '+', label: 'ro‘yxat — bir necha daqiqada' },
    { value: 1, prefix: '<', suffix: ' s', label: 'ekranlardagi yangilanish' },
    { value: 456976, prefix: '', suffix: '', label: 'kod sig‘imi har tadbirga' },
    { value: 3, prefix: '', suffix: '', label: 'rol: egasi, menejer, skaner' },
  ],
  launch: {
    title: '5 daqiqada ishga tushiring',
    sub: 'Texnik bilim shart emas — hammasi brauzerda.',
    steps: [
      { title: 'Hisob oching', text: 'Telefon raqam va parol bilan ro‘yxatdan o‘ting, kompaniyangizni yarating.' },
      { title: 'Botni ulang', text: 'Telegramda @BotFather’dan token oling va sozlamalarga qo‘ying — bot shu zahoti ishlaydi.' },
      { title: 'Jamoani qo‘shing', text: 'Menejer va skanerlarni qo‘shing, stollarni belgilang. Parollar avtomatik yaratiladi.' },
      { title: 'Tadbirni e’lon qiling', text: 'Sotuv kuni va skanerlash muddatini kiriting. Bot havolasini mijozlarga tarqating — tayyor.' },
    ],
    cta: 'Hoziroq boshlash',
  },
  faq: {
    title: 'Ko‘p so‘raladigan savollar',
    items: [
      {
        q: 'Mijozlarga ilova o‘rnatish kerakmi?',
        a: 'Yo‘q. Ro‘yxat, QR-kod va barcha xabarlar Telegramda. Ofisda esa QR qabulxonada skanerlanadi — mijoz telefonida hech narsa o‘rnatmaydi.',
      },
      {
        q: 'Nega kodlar tartib bilan emas?',
        a: 'Tasodifiy 4 harfli kod navbatdagi o‘rinni oldindan bildirmaydi va “kod savdosi”ning oldini oladi. Yakuniy tartibni faqat botdagi ro‘yxat vaqti belgilaydi.',
      },
      {
        q: 'Mijoz kech qolsa nima bo‘ladi?',
        a: 'Skanerlash muddati tugagach kelganlar kun oxiri navbatiga qo‘shiladi. Chaqiruvga kelmaganlar bir marta kun oxiriga o‘tkaziladi, ikkinchi marta kelmasa navbat bekor qilinadi.',
      },
      {
        q: 'Internet uzilib qolsa-chi?',
        a: 'Ekranlar va panellar aloqani o‘zi qayta tiklaydi va zaxira so‘rovlar bilan ishlashda davom etadi. Server holati esa ma’lumotlar bazasida — hech narsa yo‘qolmaydi.',
      },
      {
        q: 'Bir nechta filial yoki tadbir bo‘lsa?',
        a: 'Istalgancha tadbir yarating — har birining o‘z sanasi, muddati va ekrani bo‘ladi. Bot mijozga qaysi tadbirga yozilishni o‘zi taklif qiladi.',
      },
    ],
  },
  cta: {
    title: 'Keyingi sotuv kuningiz — tartibli boshlansin',
    sub: 'Ro‘yxatdan o‘ting, botni ulang va birinchi tadbiringizni bugun e’lon qiling.',
    button: 'Bepul boshlash',
    secondary: 'Hisobim bor — kirish',
  },
  footer: {
    tagline: 'Sotuv kunlari uchun onlayn navbat tizimi',
    product: 'Mahsulot',
    account: 'Hisob',
    rights: 'Barcha huquqlar himoyalangan.',
  },
  auth: {
    loginTitle: 'Xush kelibsiz',
    loginSub: 'Hisobingizga kiring — navbat sizni kutmoqda',
    registerTitle: 'Hisob yarating',
    registerSub: 'Bir daqiqa — va kompaniyangiz tizimda',
    firstName: 'Ism',
    lastName: 'Familiya',
    phone: 'Telefon raqam',
    password: 'Parol',
    passwordNew: 'Parol (kamida 6 belgi)',
    submitLogin: 'Kirish',
    submitLoginBusy: 'Kirilmoqda…',
    submitRegister: 'Hisob yaratish',
    submitRegisterBusy: 'Yaratilmoqda…',
    noAccount: 'Kompaniyangiz yo‘qmi?',
    registerLink: 'Ro‘yxatdan o‘ting',
    haveAccount: 'Hisobingiz bormi?',
    loginLink: 'Kirish',
    backHome: 'Bosh sahifa',
    panelTitle: 'Sotuv kuni — yagona tizimda',
    panelPoints: [
      'Telegram-bot ro‘yxati va QR-kodlar',
      'Adolatli navbat — ro‘yxat vaqti bo‘yicha',
      'Jonli TV-tablo va menejer paneli',
    ],
  },
}
