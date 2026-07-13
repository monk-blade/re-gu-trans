// gujarati_translator.js
// Gujarati phonetic transliteration engine for Rime using librime-qjs
//
// Transliteration scheme (IAST-inspired, phonetic):
//   Vowels: a અ, aa આ, i ઇ, ee/ii ઈ, u ઉ, oo/uu ઊ, R ઋ, RR ૠ, E ઍ, e એ, ai ઐ,
//            O ઑ, o ઓ, au ઔ, aM અં, aH અઃ, oM ઓં
//   Consonants: k ક, kh ખ, g ગ, gh ઘ, ng ઙ,
//               c/ch ચ, chh છ, j જ, jh ઝ, ny ઞ,
//               T ટ, Th ઠ, D ડ, Dh ઢ, N ણ,
//               t ત, th થ, d દ, dh ધ, n ન,
//               p પ, ph/f ફ, b બ, bh ભ, m મ,
//               y ય, r ર, l લ, L ળ, v/w વ,
//               sh શ, Sh ષ, s સ, h હ,
//               x/ksh ક્ષ, gy જ્ઞ, dv દ્વ, z ઝ
//   Digits: 0 ૦, 1 ૧, 2 ૨, 3 ૩, 4 ૪, 5 ૫, 6 ૬, 7 ૭, 8 ૮, 9 ૯
//   Virama (halant): + forces explicit halant on preceding consonant
//
// Behavior:
//   - Consonant alone carries implicit short 'a'
//   - Consonant + vowel = consonant with corresponding matra
//   - Consonant followed by another consonant = first gets virama (્)
//   - '+' forces virama explicitly
//   - Arabic digits transliterate to Gujarati digits
//   - Unknown characters pass through unchanged (punctuation, spaces)
//   - Dictionary lookup for common Gujarati words (trie-backed for speed)

const VIRAMA = '\u0ACD'

// ---------------------------------------------------------------------------
// Gujarati digits
// ---------------------------------------------------------------------------

const DIGITS = {
  '0': '\u0AE6', // ૦
  '1': '\u0AE7', // ૧
  '2': '\u0AE8', // ૨
  '3': '\u0AE9', // ૩
  '4': '\u0AEA', // ૪
  '5': '\u0AEB', // ૫
  '6': '\u0AEC', // ૬
  '7': '\u0AED', // ૭
  '8': '\u0AEE', // ૮
  '9': '\u0AEF', // ૯
}

// ---------------------------------------------------------------------------
// Vowel mappings
// ---------------------------------------------------------------------------

const VOWEL_INDEPENDENT = {
  'a':  '\u0A85', // અ
  'aa': '\u0A86', // આ
  'i':  '\u0A87', // ઇ
  'ee': '\u0A88', // ઈ
  'ii': '\u0A88', // ઈ
  'u':  '\u0A89', // ઉ
  'oo': '\u0A8A', // ઊ
  'uu': '\u0A8A', // ઊ
  'R':  '\u0A8B', // ઋ
  'RR': '\u0AE0', // ૠ
  'E':  '\u0A8D', // ઍ
  'e':  '\u0A8F', // એ
  'ai': '\u0A90', // ઐ
  'O':  '\u0A91', // ઑ
  'o':  '\u0A93', // ઓ
  'au': '\u0A94', // ઔ
  'M':  '\u0A82', // ં  (anusvara)
  'H':  '\u0A83', // ઃ  (visarga)
}

const VOWEL_MATRAS = {
  'aa': '\u0ABE', // ા
  'i':  '\u0ABF', // િ
  'ee': '\u0AC0', // ી
  'ii': '\u0AC0', // ી
  'u':  '\u0AC1', // ુ
  'oo': '\u0AC2', // ૂ
  'uu': '\u0AC2', // ૂ
  'R':  '\u0AC3', // ૃ
  'RR': '\u0AC4', // ૄ
  'E':  '\u0AC5', // ૅ
  'e':  '\u0AC7', // ે
  'ai': '\u0AC8', // ૈ
  'O':  '\u0AC9', // ૉ
  'o':  '\u0ACB', // ો
  'au': '\u0ACC', // ૌ
  'M':  '\u0A82', // ં
  'H':  '\u0A83', // ઃ
}

// ---------------------------------------------------------------------------
// Consonant mappings
// ---------------------------------------------------------------------------

const CONSONANTS = {
  'k':   '\u0A95', // ક
  'kh':  '\u0A96', // ખ
  'g':   '\u0A97', // ગ
  'gh':  '\u0A98', // ઘ
  'ng':  '\u0A99', // ઙ
  'c':   '\u0A9A', // ચ
  'ch':  '\u0A9A', // ચ
  'chh': '\u0A9B', // છ
  'j':   '\u0A9C', // જ
  'jh':  '\u0A9D', // ઝ
  'ny':  '\u0A9E', // ઞ
  'T':   '\u0A9F', // ટ
  'Th':  '\u0AA0', // ઠ
  'D':   '\u0AA1', // ડ
  'Dh':  '\u0AA2', // ઢ
  'N':   '\u0AA3', // ણ
  't':   '\u0AA4', // ત
  'th':  '\u0AA5', // થ
  'd':   '\u0AA6', // દ
  'dh':  '\u0AA7', // ધ
  'n':   '\u0AA8', // ન
  'p':   '\u0AAA', // પ
  'ph':  '\u0AAB', // ફ
  'f':   '\u0AAB', // ફ
  'b':   '\u0AAC', // બ
  'bh':  '\u0AAD', // ભ
  'm':   '\u0AAE', // મ
  'y':   '\u0AAF', // ય
  'r':   '\u0AB0', // ર
  'l':   '\u0AB2', // લ
  'L':   '\u0AB3', // ળ
  'v':   '\u0AB5', // વ
  'w':   '\u0AB5', // વ
  'sh':  '\u0AB6', // શ
  'Sh':  '\u0AB7', // ષ
  's':   '\u0AB8', // સ
  'h':   '\u0AB9', // હ
  'x':   '\u0A95\u0ACD\u0AB7', // ક્ષ
  'ksh': '\u0A95\u0ACD\u0AB7', // ક્ષ
  'gy':  '\u0A9C\u0ACD\u0A9E', // જ્ઞ
  'dv':  '\u0AA6\u0ACD\u0AB5', // દ્વ
  'z':   '\u0A9D', // ઝ
}

// ---------------------------------------------------------------------------
// Common Gujarati words dictionary
// Maps transliteration (lowercase) → Gujarati
// ---------------------------------------------------------------------------


// ---------------------------------------------------------------------------
// Apple gu-Mappings preferred overlays (distilled)
// First listed glyph is preferred when generating phonetic candidates.
// ---------------------------------------------------------------------------
const APPLE_PREFERRED = {
  'aai': 'આઈ',
  'aao': 'આઓ',
  'chh': 'છ',
  'iaa': 'ઇઆ',
  'ksh': 'ક્ષ',
  'oie': 'ોઇએ',
  'shr': 'શ્ર',
  'thh': 'ઠ',
  'aa': 'આ',
  'ae': 'એ',
  'ai': 'ઐ',
  'ao': 'આઓ',
  'au': 'ઔ',
  'bh': 'ભ',
  'ch': 'ચ',
  'dh': 'ધ',
  'ee': 'ઈ',
  'gh': 'ઘ',
  'gy': 'જ્ઞ',
  'ia': 'િયા',
  'io': 'ઇઓ',
  'jh': 'ઝ',
  'kh': 'ખ',
  'oe': 'ઓએ',
  'oi': 'ઓઇ',
  'oo': 'ઉ',
  'ph': 'ફ',
  'ra': 'ૃ',
  'rh': 'ઢ',
  'ri': 'ઋ',
  'ru': 'ઋ',
  'sh': 'શ',
  'th': 'થ',
  'tr': 'ત્ર',
  'uo': 'ુઓ',
  'a': 'અ',
  'b': 'બ',
  'c': 'ક',
  'd': 'દ',
  'e': 'એ',
  'f': 'ફ',
  'g': 'ગ',
  'h': 'હ',
  'i': 'ઇ',
  'j': 'જ',
  'k': 'ક',
  'l': 'લ',
  'm': 'મ',
  'n': 'ન',
  'o': 'ઓ',
  'p': 'પ',
  'r': 'ર',
  's': 'સ',
  't': 'ટ',
  'u': 'ઉ',
  'v': 'વ',
  'w': 'વ',
  'x': 'ક્ષ',
  'y': 'ય',
  'z': 'ઝ',
}

const WORD_DICT = {
  // Numbers
  'ek':       'એક',
  'be':       'બે',
  'tran':     'ત્રણ',
  'chaar':    'ચાર',
  'paanch':   'પાંચ',
  'chh':      'છ',
  'saat':     'સાત',
  'aath':     'આઠ',
  'nav':      'નવ',
  'das':      'દસ',
  'agyaar':   'અગિયાર',
  'baar':     'બાર',
  'ter':      'તેર',
  'chaud':    'ચૌદ',
  'pandar':   'પંદર',
  'sor':      'સોળ',
  'satar':    'સતર',
  'aadhar':   'અઢાર',
  'ogNis':    'ઓગણીસ',
  'vis':      'વીસ',
  'so':       'સો',
  'hajar':    'હજાર',
  'laakh':    'લાખ',
  'karod':    'કરોડ',

  // Common words
  'gujaraat':   'ગુજરાત',
  'gujaraatii': 'ગુજરાતી',
  'bhaarat':    'ભારત',
  'hindustaan': 'હિંદુસ્તાન',
  'ahmedaabaad':'અમદાવાદ',
  'surat':      'સુરત',
  'vadodaraa':  'વડોદરા',
  'raajkot':    'રાજકોટ',
  'bhaavnagar': 'ભાવનગર',
  'jamnagar':   'જામનગર',
  'gandhinagar':'ગાંધીનગર',

  // Pronouns
  'huM':        'હું',
  'tuM':        'તું',
  'te':         'તે',
  'tame':       'તમે',
  'tameM':      'તમં',
  'ame':        'અમે',
  'aap':        'આપ',
  'aapNe':      'આપને',
  'enee':       'એને',
  'tenee':      'તેને',
  'mujh':       'મુઝ',
  'mujhe':      'મુઝે',
  'tujh':       'તુઝ',
  'tujhe':      'તુઝે',

  // Common nouns/verbs
  'naam':       'નામ',
  'kaam':       'કામ',
  'gaaM':       'ગામ',
  'ghar':       'ઘર',
  'duniyaa':    'દુનિયા',
  'desh':       'દેશ',
  'rajy':       'રાજ્ય',
  'nagar':      'નગર',
  'shaher':     'શહેર',
  'maarga':     'માર્ગ',
  'rasta':      'રસ્તા',
  'vidyaa':     'વિદ્યા',
  'shikshaN':   'શિક્ષણ',
  'shaalaa':    'શાળા',
  'vishvavidyaalay':'વિશ્વવિદ્યાલય',
  'pustak':     'પુસ્તક',
  'kavitaa':    'કવિતા',
  'sahity':     'સાહિત્ય',
  'samachaar':  'સમાચાર',
  'akhabaar':   'અખબાર',
  'chaatr':     'છાત્ર',
  'shikshak':   'શિક્ષક',
  'vyaapaar':   'વ્યાપાર',
  'kaarobaar':  'કારોબાર',
  'dukaan':     'દુકાન',
  'paise':      'પૈસે',
  'rupiyaa':    'રૂપિયા',
  'daam':       'દામ',
  'kimat':      'કિંમત',
  'bhaav':      'ભાવ',

  // Time
  'divas':      'દિવસ',
  'raatr':      'રાત્ર',
  'raatri':     'રાત્રિ',
  'saveraa':    'સવાર',
  'saMja':      'સાંજ',
  'saayMkaal':  'સાંજકાળ',
  'prabhaat':   'પ્રભાત',
  'dopahr':     'દોપહેર',
  'samay':      'સમય',
  'ghaDi':      'ઘડી',
  'miNaT':      'મિનિટ',
  'kshaN':      'ક્ષણ',
  'kaal':       'કાળ',
  'varsh':      'વર્ષ',
  'mahinaa':    'મહિનો',
  'maas':       'માસ',
  'saptaah':    'સપ્તાહ',
  'hafto':      'હફ્તો',
  'aaj':        'આજ',
  'kaal_e':     'કાલે',
  'parso':      'પરસો',
  'kal':        'કાલ',

  // Nature
  'paani':      'પાણી',
  'aag':        'આગ',
  'havaa':      'હવા',
  'aakaash':    'આકાશ',
  'dhartii':    'ધરતી',
  'pRuthvii':   'પૃથ્વી',
  'sury':       'સૂર્ય',
  'suuraj':     'સૂરજ',
  'chandra':    'ચંદ્ર',
  'taaraa':     'તારા',
  'nadii':      'નદી',
  'samudr':     'સમુદ્ર',
  'pahaad':     'પહાડ',
  'parvat':     'પર્વત',
  'van':        'વન',
  'jungle':     'જંગલ',
  'pashu':      'પશુ',
  'pakshii':    'પક્ષી',
  'phal':       'ફળ',
  'phuul':      'ફૂલ',
  'rukh':       'રુક્ખ',
  'ped':        'પેડ',
  'vRuksh':     'વૃક્ષ',
  'biij':       'બીજ',
  'miTTii':     'મિટ્ટી',
  'bijalii':    'બિજલી',

  // People/Family
  'maataa':     'માતા',
  'maa':        'મા',
  'pitaajii':   'પિતાજી',
  'pitaa':      'પિતા',
  'baa':        'બા',
  'baapujii':   'બાપુજી',
  'dikraa':     'દીકરો',
  'dikarii':    'દીકરી',
  'betaa':      'બેટા',
  'betii':      'બેટી',
  'bhau':       'ભાઈ',
  'ben':        'બહેન',
  'dadaajii':   'દાદાજી',
  'daadii':     'દાદી',
  'naanaajii':  'નાનાજી',
  'naanii':     'નાની',
  'maasii':     'માસી',
  'maamaajii':  'મામાજી',
  'kkaakaa':    'કાકા',
  'kkaakii':    'કાકી',
  'mama':       'મામા',
  'mousii':     'મૌસી',
  'bhaai':      'ભાઈ',
  'bahiiN':     'બહીન',
  'patii':      'પતિ',
  'patnii':     'પત્ની',
  'purush':     'પુરુષ',
  'strii':      'સ્ત્રી',
  'maanav':     'માનવ',
  'vyakti':     'વ્યક્તિ',
  'jan':        'જન',
  'lok':        'લોક',
  'janaataa':   'જનતા',
  'mitr':       'મિત્ર',
  'dost':       'દોસ્ત',
  'shatru':     'શત્રુ',

  // Abstract
  'prem':       'પ્રેમ',
  'maitr':      'મૈત્ર',
  'saty':       'સત્ય',
  'jhuuTh':     'ઝૂઠ',
  'dharm':      'ધર્મ',
  'karma':      'કર્મ',
  'yog':        'યોગ',
  'gyaan':      'જ્ઞાન',
  'buddhi':     'બુદ્ધિ',
  'vivek':      'વિવેક',
  'shakti':     'શક્તિ',
  'bal':        'બળ',
  'aashaa':     'આશા',
  'niraashaa':  'નિરાશા',
  'khushii':    'ખુશી',
  'dukh':       'દુઃખ',
  'shaaNti':    'શાંતિ',
  'anand':      'આનંદ',
  'hriday':     'હૃદય',
  'aatm':       'આત્મ',
  'aashirvaad': 'આશીર્વાદ',
  'prarthanaa': 'પ્રાર્થના',
  'puujaa':     'પૂજા',
  'sevaa':      'સેવા',
  'tyaag':      'ત્યાગ',
  'daan':       'દાન',
  'paap':       'પાપ',
  'punya':      'પુણ્ય',
  'svaatantry': 'સ્વાતંત્ર્ય',
  'aazaadii':   'આઝાદી',
  'sammaan':    'સન્માન',
  'apamaan':    'અપમાન',
  'laaj':       'લાજ',
  'sharm':      'શરમ',
  'himmat':     'હિંમત',
  'sahas':      'સાહસ',
  'shourya':    'શૌર્ય',
  'krodh':      'ક્રોધ',
  'lobh':       'લોભ',
  'moha':       'મોહ',
  'ahankaar':   'અહંકાર',
  'maan':       'માન',
  'sneh':       'સ્નેહ',
  'kaaruNya':   'કારુણ્ય',
  'dayaa':      'દયા',
  'kripaa':     'કૃપા',
  'krupa':      'કૃપા',
  'anugrah':    'અનુગ્રહ',

  // Colors
  'laal':       'લાલ',
  'haraa':      'હરો',
  'hariyaal':   'હરિયાળ',
  'piilaa':     'પીળો',
  'niilaa':     'નીલો',
  'ujLuu':      'ઉજ્જળ',
  'kaaLuu':     'કાળો',
  'safed':      'સફેદ',
  'sufed':      'સફેદ',
  'bhauraa':    'ભૂરો',
  'naarangii':  'નારંગી',
  'gulaabii':   'ગુલાબી',
  'bainganii':  'બૈંગણી',

  // Food
  'rotlII':     'રોટલી',
  'shaak':      'શાક',
  'daal':       'દાળ',
  'bhaat':      'ભાત',
  'khiichDii':  'ખિચડી',
  'dokLaa':     'ઢોકળા',
  'khamaaN':    'ખમણ',
  'fafDaa':     'ફાફડા',
  'jalebi':     'જલેબી',
  'shrikhaND':  'શ્રીખંડ',
  'basuNDii':   'બસુંદી',
  'gharii':     'ઘરી',
  'undhiyuu':   'ઉંધિયું',
  'thepLaa':    'થેપલા',
  'gathiyaa':   'ગાંઠિયા',
  'paatraa':    'પાત્રા',
  'laapsii':    'લાપસી',
  'suurati-jaamnagar': 'સુરતી-જામનગર',
  'maLaa-ii':   'મળાઈ',
  'chaash':     'છાશ',
  'dudh':       'દૂધ',
  'ghee':       'ઘી',
  'tel':        'તેલ',
  'miThaaii':   'મિઠાઈ',
  'miThuu':     'મીઠું',
  'tiikh':      'તીખ',
  'kaDvvuu':    'કડવું',
  'khattuu':    'ખાટ્ટું',
  'nammuuk':    'નમ્મક',

  // Verbs
  'karo':       'કરો',
  'karvu':      'કરવું',
  'bolo':       'બોલો',
  'bolvu':      'બોલવું',
  'jaao':       'જાઓ',
  'jaavu':      'જાવું',
  'aavo':       'આવો',
  'aavvu':      'આવવું',
  'khaavo':     'ખાવો',
  'khaavu':     'ખાવું',
  'piivo':      'પીવો',
  'piivu':      'પીવું',
  'paDho':      'પઢો',
  'paDhvuu':    'પઢવું',
  'laakho':     'લખો',
  'laakhvuu':   'લખવું',
  'sunoo':      'સાંભળો',
  'sunvuu':     'સાંભળવું',
  'dekho':      'જુઓ',
  'jovuu':      'જોવું',
  'utho':       'ઉઠો',
  'uThvuu':     'ઉઠવું',
  'baiso':      'બેસો',
  'baisvuu':    'બેસવું',
  'hasso':      'હસો',
  'hasvuu':     'હસવું',
  'rovo':       'રડો',
  'rovu':       'રડવું',
  'doudo':      'દોડો',
  'doudvuu':    'દોડવું',
  'raho':       'રહો',
  'rahvuu':     'રહેવું',
  'mariye':     'મરીએ',
  'marvu':      'મરવું',
  'dekhaay':    'દેખાય',
  'thaay':      'થાય',
  'hoy':        'હોય',
  'nathi':      'નથી',
  'chhe':       'છે',
  'hato':       'હતો',
  'hati':       'હતી',
  'hashe':      'હશે',
  'karish':     'કરીશ',
  'jaaiish':    'જઈશ',
  'aaviish':    'આવીશ',
  'kariishuM':  'કરીશું',
  'jaaiishuM':  'જઈશું',
  'aaviishuM':  'આવીશું',
  'karishuM':   'કરીશું',

  // Alternate spellings / fuzzy matches
  'ave':        'આવે',
  'aavvu':      'આવવું',
  'aavjo':      'આવજો',
  'aave':       'આવે',

  // Adjectives/Adverbs
  'saaru':      'સારું',
  'saarii':     'સારી',
  'saaro':      'સારો',
  'naaLu':      'નાળું',
  'naaLii':     'નાળી',
  'naaLo':      'નાળો',
  'maDvu':      'મધ્ય',
  'nava':       'નવા',
  'navi':       'નવી',
  'navaa':      'નવું',
  'juna':       'જૂના',
  'junii':      'જૂની',
  'junu':       'જૂનું',
  'motu':       'મોટું',
  'motii':      'મોટી',
  'moto':       'મોટો',
  'naanu':      'નાનું',
  'naanii':     'નાની',
  'naano':      'નાનો',
  'uuchu':      'ઊંચું',
  'uuchii':     'ઊંચી',
  'uucho':      'ઊંચો',
  'laambu':     'લાંબું',
  'laambii':    'લાંબી',
  'laambo':     'લાંબો',
  'thaaNDu':    'ઠંડું',
  'thaaNDii':   'ઠંડી',
  'thaaNDo':    'ઠંડો',
  'gaRmu':      'ગરમ',
  'gaRmii':     'ગરમી',
  'tej':        'તેજ',
  'dhaaLuu':    'ઢાળું',
  'dhaaLii':    'ઢાળી',
  'dhaaLo':     'ઢાળો',
  'sidaLuu':    'સીધું',
  'sidaLii':    'સીધી',
  'sidaLo':     'સીધો',
  'gola':       'ગોળ',
  'chaursu':    'ચોરસ',
  'trikuN':     'ત્રિકોણ',
  'aage':       'આગળ',
  'paaChu':     'પાછળ',
  'uupar':      'ઉપર',
  'niiche':     'નીચે',
  'daaM':       'ડાબું',
  'jaMvu':      'જમણું',
  'biich':      'બીચ',
  'bahaar':     'બહાર',
  'andar':      'અંદર',
  'paas':       'પાસ',
  'duur':       'દૂર',
  'paheLaa':    'પહેલાં',
  'pachhii':    'પછી',
  'aaje':       'આજે',
  'kaaLe':      'કાલે',
  'hameShaa':   'હમેશા',
  'ekla':       'એકલા',
  'saaThe':     'સાથે',
  'sarv':       'સર્વ',
  'sab':        'સબ',
  'badhaa':     'બધા',
  'koi':        'કોઈ',
  'kaaii':      'કઈ',
  'shu':        'શું',
  'kaheM':      'કેમ',
  'kyaare':     'ક્યારે',
  'kyaM':       'ક્યાં',
  'kone':       'કોને',
  'shuuM':      'શું',
  'kahe':       'કહે',
  'bolaav':     'બોલાવ',
  'jaai':       'જાઈ',
  'thaai':      'થાઈ',
  'dekhii':     'દેખી',
  'saaMbhLii':  'સાંભળી',

  // Phrases
  'namaste':    'નમસ્તે',
  'jay-hind':   'જય હિંદ',
  'jay-gujaraat':'જય ગુજરાત',
  'kem-chho':   'કેમ છો',
  'huM-maajaa-maa':'હું મજામાં',
  'dhanyavaad': 'ધન્યવાદ',
  'aabhaar':    'આભાર',
  'maaf-karjo': 'માફ કરજો',
  'aavjo':      'આવજો',
  'jaajo':      'જાજો',
  'subh-prabhaat':'શુભ પ્રભાત',
  'subh-raatr': 'શુભ રાત્રિ',
  'shubhakaamnaa':'શુભકામના',
  'hardik-aabhinaMdan':'હાર્દિક અભિનંદન',
  'janmadin-mubarak':'જન્મદિન મુબારક',

  // Modern terms
  'saMgaNak':   'સંગણક',
  'kaMpuTar':   'કમ્પ્યુટર',
  'moobaail':   'મોબાઈલ',
  'foon':       'ફોન',
  'iMTarneT':   'ઈન્ટરનેટ',
  'sophtaveyar':'સોફ્ટવેર',
  'haDaver':    'હાર્ડવેર',
  'sauchaaLaya':'સૌચાલય',
  'vimaan':     'વિમાન',
  'relgDDii':   'રેલગાડી',
  'bas':        'બસ',
  'gDDii':      'ગાડી',
  'moTar':      'મોટર',
  'saiakal':    'સાઈકલ',

  // Body parts
  'aankh':      'આંખ',
  'aamkh':      'આંખ',
  'kaan':       'કાન',
  'naak':       'નાક',
  'moM':        'મોં',
  'haath':      'હાથ',
  'pag':        'પગ',
  'daaMt':      'દાંત',
  'magaj':      'મગજ',
  'peT':        'પેટ',
  'piiTh':      'પીઠ',
  'aangLii':    'આંગળી',
  'aamgLii':    'આંગળી',
  'nakha':      'નખ',

  // Alternate spellings (phonetic vs dictionary)
  'chatr':      'છત્ર',
  'chhatr':     'છત્ર',
  'chhaatr':    'છાત્ર',
  'naL':        'નળ',
  'naaL':       'નાળ',
  'nal':        'નળ',

  // Days
  'somvaar':    'સોમવાર',
  'maNgaLvaar': 'મંગળવાર',
  'budhvaar':   'બુધવાર',
  'guruvaar':   'ગુરુવાર',
  'shukrvaar':  'શુક્રવાર',
  'shanivaar':  'શનિવાર',
  'ravivaar':   'રવિવાર',

  // Gregorian months
  'jaanyuaarii':'જાન્યુઆરી',
  'phebruaarii':'ફેબ્રુઆરી',
  'maarch':     'માર્ચ',
  'epril':      'એપ્રિલ',
  'me':         'મે',
  'juun':       'જૂન',
  'julaaii':    'જુલાઈ',
  'ogasT':      'ઓગસ્ટ',
  'sapTembar':  'સપ્ટેમ્બર',
  'okTobar':    'ઓક્ટોબર',
  'novembar':   'નવેમ્બર',
  'Disembar':   'ડિસેમ્બર',

  // Gujarati months
  'chaitr':     'ચૈત્ર',
  'vaishaakh':  'વૈશાખ',
  'jheTh':      'જેઠ',
  'aashaaDh':   'આષાઢ',
  'shraavaN':   'શ્રાવણ',
  'bhaadarvo':  'ભાદરવો',
  'aaso':       'આસો',
  'kaartak':    'કારતક',
  'maagasr':    'માગસર',
  'posh':       'પોષ',
  'mahaa':      'મહા',
  'phaagaN':    'ફાગણ',

  // Additional verbs
  'laavo':      'લાવો',
  'laavvu':     'લાવવું',
  'mokLo':      'મોકળો',
  'mokLvu':     'મોકળવું',
  'khoLo':      'ખોળો',
  'khoLvu':     'ખોલવું',
  'chaalo':     'ચાલો',
  'chaalvu':    'ચાલવું',
  'roko':       'રોકો',
  'rokvu':      'રોકવું',
  'vadhaaro':   'વધારો',
  'ghaTaado':   'ઘટાડો',

  // Common nouns/adjectives — ranking comes from Apple lexicon weights,
  // not hand-baked entries (96k+ romans in gu_lexicon_blob.json).
  'samasya':    'સમસ્યા',
  'ukel':       'ઉકેલ',
  'rasto':      'રસ્તો',
  'ghaDiyaaL':  'ઘડિયાળ',
  'vichaar':    'વિચાર',
  'beThak':     'બેઠક',
  'sabhaa':     'સભા',
  'samiti':     'સમિતિ',
  'manTan':     'મંતન',
  'yojanaa':    'યોજના',
  'kaamgiri':   'કામગિરી',
  'shikshit':   'શિક્ષિત',
  'anapaDh':    'અનપઢ',
  'laayak':     'લાયક',
  'beimaan':    'બેઈમાન',
  'iimaanDaar': 'ઈમાનદાર',
  'dhani':      'ધની',
  'garib':      'ગરીબ',
  'svaasthya':  'સ્વાસ્થ્ય',
  'rogo':       'રોગ',
}

// ---------------------------------------------------------------------------
// Trie for fast prefix matching
// ---------------------------------------------------------------------------

class TrieNode {
  constructor() {
    this.children = new Map()
    this.value = null
  }
}

class Trie {
  constructor() {
    this.root = new TrieNode()
  }

  insert(key, value) {
    let node = this.root
    for (const char of key) {
      if (!node.children.has(char)) {
        node.children.set(char, new TrieNode())
      }
      node = node.children.get(char)
    }
    node.value = value
  }

  findExact(key) {
    let node = this.root
    for (const char of key) {
      if (!node.children.has(char)) return null
      node = node.children.get(char)
    }
    return node.value
  }

  findPrefixMatches(prefix, limit = 20) {
    return this.findPrefixEntries(prefix, limit).map((e) => e.value)
  }

  // Returns { key, value } for roman keys under prefix (includes exact key if present).
  findPrefixEntries(prefix, limit = 20) {
    let node = this.root
    for (const char of prefix) {
      if (!node.children.has(char)) return []
      node = node.children.get(char)
    }
    const matches = []
    this._collectEntries(node, prefix, matches, limit)
    return matches
  }

  _collectEntries(node, keySoFar, matches, limit) {
    if (matches.length >= limit) return
    if (node.value !== null) {
      matches.push({ key: keySoFar, value: node.value })
    }
    for (const [ch, child] of node.children.entries()) {
      this._collectEntries(child, keySoFar + ch, matches, limit)
      if (matches.length >= limit) return
    }
  }
}

const DICT_TRIE = new Trie()
for (const [key, value] of Object.entries(WORD_DICT)) {
  DICT_TRIE.insert(key, value)
}

// ---------------------------------------------------------------------------
// Distilled Apple lexicon / exceptions (loaded from JSON blob)
// ---------------------------------------------------------------------------

const LEXICON_BLOB_PATHS = [
  'gu_lexicon_blob.json',
  'js/gu_lexicon_blob.json',
  '~/Library/Rime/js/gu_lexicon_blob.json',
  '~/Library/Rime/gu_lexicon_blob.json',
]

let APPLE_EXCEPTIONS = new Map()
let APPLE_LEXICON = new Map()
let APPLE_WEIGHTS = new Map() // roman → corpus/Apple weight (general ranking)
let KNOWN_WORDS = new Set()
let LEXICON_LOADED = false

// Candidate tiers — primary sort key (lower = better). Matches macOS-style lists:
// exact lexicon → latin echo → phonetic → prefix completions.
const TIER_EXACT = 0
const TIER_DICT = 1   // phonetic form attested via native wordlist / stem (macOS-like)
const TIER_LATIN = 2
const TIER_PHONETIC = 3
const TIER_PREFIX = 4

function rememberKnownWord(word) {
  if (word) KNOWN_WORDS.add(word)
}

for (const value of Object.values(WORD_DICT)) {
  rememberKnownWord(value)
}

function lexiconWeight(roman) {
  if (!roman) return 0
  return APPLE_WEIGHTS.get(String(roman).toLowerCase()) || 0
}

function loadTextViaEnv(env, absolutePath) {
  if (!absolutePath) return null
  if (env && typeof env.loadFile === 'function') {
    try {
      const text = env.loadFile(absolutePath)
      if (text) return text
    } catch (e) {
      // try next path
    }
  }
  if (env && typeof env.fileExists === 'function') {
    try {
      if (!env.fileExists(absolutePath)) return null
    } catch (e) {
      return null
    }
  }
  return readFileText(absolutePath)
}

function loadLexiconBlob(env) {
  if (LEXICON_LOADED) return
  LEXICON_LOADED = true

  const paths = []
  if (env && env.userDataDir) {
    paths.push(env.userDataDir + '/js/gu_lexicon_blob.json')
    paths.push(env.userDataDir + '/gu_lexicon_blob.json')
  }
  for (const p of LEXICON_BLOB_PATHS) {
    paths.push(resolveUserPath(p))
  }

  let text = null
  let used = null
  for (const p of paths) {
    text = loadTextViaEnv(env, p)
    if (text) {
      used = p
      break
    }
  }
  if (!text) {
    console.log('$qjs$ lexicon blob missing; using WORD_DICT only')
    return
  }
  try {
    const data = JSON.parse(text)
    if (data.exceptions) {
      for (const [k, v] of Object.entries(data.exceptions)) {
        const word = typeof v === 'string' ? v : (v && v.text) || ''
        if (!word) continue
        APPLE_EXCEPTIONS.set(String(k).toLowerCase(), word)
        DICT_TRIE.insert(String(k).toLowerCase(), word)
        rememberKnownWord(word)
        APPLE_WEIGHTS.set(String(k).toLowerCase(), 1000)
      }
    }
    if (data.weights) {
      for (const [k, w] of Object.entries(data.weights)) {
        const n = Number(w)
        if (Number.isFinite(n)) APPLE_WEIGHTS.set(String(k).toLowerCase(), n)
      }
    }
    if (data.lexicon) {
      let n = 0
      for (const [k, v] of Object.entries(data.lexicon)) {
        const key = String(k).toLowerCase()
        const word = typeof v === 'string' ? v : (v && v.text) || ''
        if (!word) continue
        APPLE_LEXICON.set(key, word)
        rememberKnownWord(word)
        if (!DICT_TRIE.findExact(key)) {
          DICT_TRIE.insert(key, word)
        }
        if (!APPLE_WEIGHTS.has(key) && v && typeof v === 'object' && Number.isFinite(Number(v.weight))) {
          APPLE_WEIGHTS.set(key, Number(v.weight))
        }
        n += 1
      }
      console.log(
        '$qjs$ lexicon loaded entries=' + n +
        ' weights=' + APPLE_WEIGHTS.size +
        ' exceptions=' + APPLE_EXCEPTIONS.size +
        ' from=' + used
      )
    }
  } catch (e) {
    console.error('$qjs$ lexicon parse error:', e.message)
  }
}



// ---------------------------------------------------------------------------
// Language model and personalization
// ---------------------------------------------------------------------------

const USER_LM_DEFAULT_PATH = '~/Library/Rime/gujarati.user.tsv'
const UNIGRAM_PATH = 'js/lm/unigram.tsv'
const BIGRAM_PATH = 'js/lm/bigram.tsv'
const TRIGRAM_PATH = 'js/lm/trigram.tsv'
const LM_WEIGHTS = {
  unigram: 0.6,
  bigram: 0.9,
  user: 0.6,
}
let TRIGRAM_WEIGHT = 1.1
const CORE_BIGRAMS = new Map([
  ['મારું|નામ', 1200],
  ['હું|નામ', 900],
  ['ગુજરાતી|ભાષા', 800],
])
const USER_FLUSH_THRESHOLD = 8
const SCORE_CACHE_LIMIT = 500

function resolveUserPath(path) {
  if (!path || typeof path !== 'string') return path
  if (path.startsWith('~/') && typeof os !== 'undefined' && os.homedir) {
    return os.homedir() + path.slice(1)
  }
  return path
}

function readFileText(path) {
  if (typeof read !== 'function') return null
  try {
    return read(path)
  } catch (e) {
    return null
  }
}

function readFileTextFromPaths(paths) {
  for (const path of paths) {
    const text = readFileText(path)
    if (text) return text
  }
  return null
}

function loadUnigramLM(paths) {
  const text = readFileTextFromPaths(paths)
  const map = new Map()
  let max = 1
  if (!text) return { map, max }
  const lines = text.split(/\r?\n/)
  for (const line of lines) {
    if (!line) continue
    const parts = line.split('\t')
    if (parts.length < 2) continue
    const word = parts[0]
    const count = Number(parts[1])
    if (!word || !Number.isFinite(count)) continue
    map.set(word, count)
    if (count > max) max = count
  }
  return { map, max }
}

function loadBigramLM(paths) {
  const text = readFileTextFromPaths(paths)
  const map = new Map()
  let max = 1
  if (!text) return { map, max }
  const lines = text.split(/\r?\n/)
  for (const line of lines) {
    if (!line) continue
    const parts = line.split('\t')
    if (parts.length < 3) continue
    const prev = parts[0]
    const word = parts[1]
    const count = Number(parts[2])
    if (!prev || !word || !Number.isFinite(count)) continue
    map.set(prev + '|' + word, count)
    if (count > max) max = count
  }
  for (const [key, count] of CORE_BIGRAMS.entries()) {
    const existing = map.get(key) || 0
    const next = Math.max(existing, count)
    map.set(key, next)
    if (next > max) max = next
  }
  return { map, max }
}

function loadTrigramLM(paths) {
  const text = readFileTextFromPaths(paths)
  const map = new Map()
  let max = 1
  if (!text) return { map, max }
  const lines = text.split(/\r?\n/)
  for (const line of lines) {
    if (!line) continue
    const parts = line.split('\t')
    if (parts.length < 4) continue
    const prev2 = parts[0]
    const prev1 = parts[1]
    const word = parts[2]
    const count = Number(parts[3])
    if (!prev2 || !prev1 || !word || !Number.isFinite(count)) continue
    map.set(prev2 + '|' + prev1 + '|' + word, count)
    if (count > max) max = count
  }
  return { map, max }
}

function loadUserLM(path) {
  const text = readFileText(path)
  const wordCounts = new Map()
  const bigramCounts = new Map()
  if (!text) return { wordCounts, bigramCounts }
  const lines = text.split(/\r?\n/)
  for (const line of lines) {
    if (!line) continue
    const parts = line.split('\t')
    if (parts.length === 2) {
      const word = parts[0]
      const count = Number(parts[1])
      if (!word || !Number.isFinite(count)) continue
      wordCounts.set(word, count)
    } else if (parts.length >= 3) {
      const prev = parts[0]
      const word = parts[1]
      const count = Number(parts[2])
      if (!prev || !word || !Number.isFinite(count)) continue
      bigramCounts.set(prev + '|' + word, count)
    }
  }
  return { wordCounts, bigramCounts }
}

function writeUserLM(path, wordCounts, bigramCounts) {
  if (typeof write !== 'function') return false
  const lines = []
  for (const [word, count] of wordCounts.entries()) {
    lines.push(word + '\t' + count)
  }
  for (const [key, count] of bigramCounts.entries()) {
    const [prev, word] = key.split('|')
    lines.push(prev + '\t' + word + '\t' + count)
  }
  const content = lines.join('\n') + '\n'
  try {
    write(path, content)
    return true
  } catch (e) {
    return false
  }
}

let UNIGRAM_LM = { map: new Map(), max: 1 }
let BIGRAM_LM = { map: new Map(), max: 1 }
let TRIGRAM_LM = { map: new Map(), max: 1 }
let STEM_FREQ = new Map()
let LM_LOADED = false
let USER_LM_PATH = resolveUserPath(USER_LM_DEFAULT_PATH)
let USER_LM = loadUserLM(USER_LM_PATH)
let USER_LM_DIRTY = false
let USER_LM_PENDING_WRITES = 0
const SCORE_CACHE = new Map()

const GU_SUFFIXES = [
  'માંથી', 'વાળું', 'વાળી', 'વાળા', 'વાળો', 'વું', 'વા',
  'માં', 'થી', 'ની', 'નો', 'ના', 'ને', 'નું', 'નાં',
  'શે', 'શો', 'શું', 'તું', 'તો', 'તા', 'તી', 'તાં',
  'ે', 'ો', 'ા', 'ી', 'ું', 'ાં',
]

function loadLanguageModels(env) {
  if (LM_LOADED) return
  LM_LOADED = true
  const uniPaths = []
  const stemPaths = []
  if (env && env.userDataDir) {
    uniPaths.push(env.userDataDir + '/js/lm/unigram.tsv')
    uniPaths.push(env.userDataDir + '/lm/unigram.tsv')
    stemPaths.push(env.userDataDir + '/js/lm/stems.json')
    stemPaths.push(env.userDataDir + '/lm/stems.json')
  }
  uniPaths.push(resolveUserPath('~/Library/Rime/js/lm/unigram.tsv'))
  uniPaths.push(resolveUserPath('~/Library/Rime/lm/unigram.tsv'))
  stemPaths.push(resolveUserPath('~/Library/Rime/js/lm/stems.json'))

  let uniText = null
  for (const p of uniPaths) {
    uniText = loadTextViaEnv(env, p)
    if (uniText) break
  }
  if (uniText) {
    UNIGRAM_LM = loadUnigramLMFromText(uniText)
    console.log('$qjs$ unigram loaded entries=' + UNIGRAM_LM.map.size + ' max=' + UNIGRAM_LM.max)
  } else {
    console.log('$qjs$ unigram missing')
  }

  BIGRAM_LM = loadBigramLM([BIGRAM_PATH, 'lm/bigram.tsv'])
  TRIGRAM_LM = loadTrigramLM([TRIGRAM_PATH, 'lm/trigram.tsv'])

  let stemText = null
  for (const p of stemPaths) {
    stemText = loadTextViaEnv(env, p)
    if (stemText) break
  }
  if (stemText) {
    try {
      const data = JSON.parse(stemText)
      for (const [k, v] of Object.entries(data)) {
        const n = Number(v)
        if (k && Number.isFinite(n)) STEM_FREQ.set(k, n)
      }
      console.log('$qjs$ stems loaded entries=' + STEM_FREQ.size)
    } catch (e) {
      console.error('$qjs$ stems parse error:', e.message)
    }
  }
}

function loadUnigramLMFromText(text) {
  const map = new Map()
  let max = 1
  if (!text) return { map, max }
  const lines = text.split(/\r?\n/)
  for (const line of lines) {
    if (!line) continue
    const parts = line.split('\t')
    if (parts.length < 2) continue
    const word = parts[0]
    const count = Number(parts[1])
    if (!word || !Number.isFinite(count)) continue
    map.set(word, count)
    if (count > max) max = count
  }
  return { map, max }
}

/** Native-dict / stem validity score — the scalable macOS/IndicXlit rescoring signal. */
function dictionaryValidity(text) {
  if (!text) return { score: 0, attested: false, evidence: 0 }
  const uni = UNIGRAM_LM.map.get(text) || 0
  let stemHit = STEM_FREQ.get(text) || 0
  for (const suf of GU_SUFFIXES) {
    if (text.length <= suf.length + 1) continue
    if (!text.endsWith(suf)) continue
    const stem = text.slice(0, -suf.length)
    if (!stem) continue
    stemHit = Math.max(stemHit, STEM_FREQ.get(stem) || 0)
    // attested conjugations of the same stem (ફાવે / ફાવો / ફાવવું)
    for (const ext of ['ે', 'ો', 'ા', 'ી', 'ું', 'વું', 'તું', 'વા']) {
      const form = stem + ext
      stemHit = Math.max(stemHit, UNIGRAM_LM.map.get(form) || 0, STEM_FREQ.get(form) || 0)
    }
  }
  const evidence = Math.max(uni, stemHit)
  // Penalize awkward virama clusters for pure inventions
  let virama = 0
  for (const ch of text) if (ch === '\u0ACD') virama += 1
  const viramaPenalty = virama * 0.25
  const score = Math.log1p(evidence) - viramaPenalty
  return { score: Math.max(0, score), attested: evidence > 0, evidence }
}

function normalizedScore(count, max) {
  if (!count || !max) return 0
  return Math.log1p(count) / Math.log1p(max)
}

function userBoost(count) {
  if (!count) return 0
  return Math.min(LM_WEIGHTS.user, Math.log1p(count) / 5)
}

function cachedScore(key) {
  if (SCORE_CACHE.has(key)) return SCORE_CACHE.get(key)
  return null
}

function setCachedScore(key, value) {
  if (SCORE_CACHE.size > SCORE_CACHE_LIMIT) {
    SCORE_CACHE.clear()
  }
  SCORE_CACHE.set(key, value)
}

function ensureUserLM(path) {
  const resolved = resolveUserPath(path)
  if (resolved && resolved !== USER_LM_PATH) {
    USER_LM_PATH = resolved
    USER_LM = loadUserLM(USER_LM_PATH)
  }
}

function getContextPrevWord(env) {
  try {
    if (env && env.engine && env.engine.context) {
      const ctx = env.engine.context
      if (typeof ctx.get_commit_text === 'function') {
        const text = ctx.get_commit_text()
        return lastWord(text)
      }
      if (typeof ctx.commit_text === 'function') {
        const text = ctx.commit_text()
        return lastWord(text)
      }
      if (typeof ctx.get_preedit === 'function') {
        const text = ctx.get_preedit()
        return lastWord(text)
      }
    }
  } catch (e) {
    return ''
  }
  return ''
}

function lastWord(text) {
  if (!text || typeof text !== 'string') return ''
  const matches = text.match(/[\u0A80-\u0AFF]+|[A-Za-z]+/g)
  if (!matches || matches.length === 0) return ''
  return matches[matches.length - 1]
}

function getContextPrevWords(env) {
  try {
    if (env && env.engine && env.engine.context) {
      const ctx = env.engine.context
      let text = ''
      if (typeof ctx.get_commit_text === 'function') {
        text = ctx.get_commit_text()
      } else if (typeof ctx.commit_text === 'function') {
        text = ctx.commit_text()
      } else if (typeof ctx.get_preedit === 'function') {
        text = ctx.get_preedit()
      }
      if (!text) return []
      const matches = text.match(/[\u0A80-\u0AFF]+|[A-Za-z]+/g)
      if (!matches || matches.length === 0) return []
      return matches.slice(-2)
    }
  } catch (e) {
    return []
  }
  return []
}

// ---------------------------------------------------------------------------
// Token set for fast tokenization
// ---------------------------------------------------------------------------

const TOKEN_SET = new Set([
  // Length 3
  'chh', 'ksh',
  // Length 2
  'kh', 'gh', 'ng', 'ch', 'Th', 'Dh', 'Sh', 'ph', 'bh', 'dv', 'gy', 'ny', 'jh',
  'aa', 'ee', 'ii', 'oo', 'uu', 'ai', 'au', 'RR',
  'th', 'dh', 'sh',
  // Length 1
  'a', 'i', 'u', 'e', 'o',
  'k', 'g', 'j', 'T', 'D', 'N', 't', 'd', 'n', 'p', 'b', 'm', 'y', 'r', 'l', 'v', 's', 'h', 'L',
  'c', 'f', 'w', 'x', 'z',
  'R', 'E', 'O', 'M', 'H',
  '+',
])

const MAX_TOKEN_LEN = 3

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isGujaratiConsonantCodePoint(code) {
  return code >= 0x0A95 && code <= 0x0AB9 && code !== 0x0AB1 && code !== 0x0AB4
}

function endsWithConsonantWithImplicitA(str) {
  if (str.length === 0) return false
  const lastCode = str.charCodeAt(str.length - 1)
  return isGujaratiConsonantCodePoint(lastCode)
}


function applePreferredToken(input, i) {
  // Longest-match against APPLE_PREFERRED keys
  let best = null
  let bestLen = 0
  const slice = input.slice(i)
  for (const key of Object.keys(APPLE_PREFERRED)) {
    if (key.length > bestLen && slice.startsWith(key)) {
      best = key
      bestLen = key.length
    }
  }
  if (!best) return null
  return { key: best, value: APPLE_PREFERRED[best], len: bestLen }
}

function tokenize(input) {
  const tokens = []
  let i = 0
  while (i < input.length) {
    let matched = false
    for (let len = MAX_TOKEN_LEN; len >= 1; len--) {
      if (i + len <= input.length) {
        const substr = input.substring(i, i + len)
        if (TOKEN_SET.has(substr)) {
          tokens.push(substr)
          i += len
          matched = true
          break
        }
      }
    }
    if (!matched) {
      tokens.push(input[i])
      i++
    }
  }
  return tokens
}

function transliterateTokens(tokens) {
  let result = ''

  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i]
    const nextToken = tokens[i + 1]

    if (VOWEL_INDEPENDENT[token] !== undefined) {
      if (endsWithConsonantWithImplicitA(result)) {
        if (token === 'a') {
          // 'a' after consonant = implicit short 'a'; no change
        } else {
          const matra = VOWEL_MATRAS[token]
          if (matra !== undefined) {
            const consonant = result[result.length - 1]
            result = result.slice(0, -1) + consonant + matra
          } else {
            result += VOWEL_INDEPENDENT[token]
          }
        }
      } else {
        result += VOWEL_INDEPENDENT[token]
      }
    } else if (CONSONANTS[token] !== undefined) {
      const consChar = CONSONANTS[token]
      if (nextToken !== undefined && CONSONANTS[nextToken] !== undefined) {
        result += consChar + VIRAMA
      } else if (nextToken === '+') {
        result += consChar + VIRAMA
      } else {
        result += consChar
      }
    } else if (token === '+') {
      if (endsWithConsonantWithImplicitA(result)) {
        result += VIRAMA
      }
      // '+' is consumed without output when not applicable
    } else if (DIGITS[token] !== undefined) {
      result += DIGITS[token]
    } else {
      result += token
    }
  }

  return result
}

function transliterate(input) {
  const tokens = tokenize(input)
  return transliterateTokens(tokens)
}

// ---------------------------------------------------------------------------
// Phonetic alternate form generator
// Generates alternate spellings by inserting implicit 'a' between
// consecutive consonant characters, handling variations like
// nmste → namste → namaste for dictionary lookup.
// ---------------------------------------------------------------------------

const MAX_ALT_FORMS = 64
const MAX_ALT_INSERTIONS = 2

// Phonetic confusions users actually type (macOS fuzzy mapping).
// sh↔Sh covers પોશ vs પોષ; t↔T covers કેત vs કેટ; endings cover િ vs ી, u vs ું.
const CONFUSION_MAP = {
  'ch': ['chh'],
  'chh': ['ch'],
  't': ['T'],
  'T': ['t'],
  'd': ['D'],
  'D': ['d'],
  's': ['sh', 'Sh'],
  'sh': ['Sh', 's'],
  'Sh': ['sh', 's'],
  'n': ['N'],
  'N': ['n'],
  'l': ['L'],
  'L': ['l'],
}

const ENDING_VARIANTS = {
  'i': ['ii', 'ee'],
  'ii': ['i'],
  'ee': ['i', 'ii'],
  'u': ['uu', 'un', 'um'],
  'uu': ['u'],
  'un': ['u', 'um'],
  'um': ['u', 'un'],
  'a': ['aa'],
  'aa': ['a'],
}

/** Extra roman queries for lexicon lookup (poshatu ↔ poshatun, ketli ↔ keTlii). */
function withEndingVariants(s) {
  const out = new Set([s])
  for (const [from, tos] of Object.entries(ENDING_VARIANTS)) {
    if (s.length <= from.length) continue
    if (!s.endsWith(from)) continue
    const stem = s.slice(0, -from.length)
    for (const to of tos) out.add(stem + to)
  }
  return out
}

/** Replace every occurrence position of digraph/char confusion (not only first). */
function applyConfusionOnce(s, from, to) {
  const out = []
  let idx = 0
  while (idx <= s.length - from.length) {
    const at = s.indexOf(from, idx)
    if (at < 0) break
    out.push(s.slice(0, at) + to + s.slice(at + from.length))
    idx = at + 1
  }
  return out
}

function generateAlternateForms(input) {
  const forms = new Set()
  forms.add(input)

  function expand(s, depth) {
    if (depth >= MAX_ALT_INSERTIONS) return
    for (let i = 0; i < s.length - 1; i++) {
      const pair = s.substring(i, i + 2)
      if ((s[i] in CONSONANTS) && (s[i + 1] in CONSONANTS) && !TOKEN_SET.has(pair)) {
        const expanded = s.slice(0, i + 1) + 'a' + s.slice(i + 1)
        if (forms.size < MAX_ALT_FORMS && !forms.has(expanded)) {
          forms.add(expanded)
          expand(expanded, depth + 1)
        }
      }
    }

    for (let i = 1; i < s.length - 1; i++) {
      if (s[i] !== 'a') continue
      if (!(s[i - 1] in CONSONANTS) || !(s[i + 1] in CONSONANTS)) continue
      const expanded = s.slice(0, i) + 'aa' + s.slice(i + 1)
      if (forms.size < MAX_ALT_FORMS && !forms.has(expanded)) {
        forms.add(expanded)
        expand(expanded, depth + 1)
      }
    }

    // Prefer longer confusion keys first (chh before ch, sh before s)
    const keys = Object.keys(CONFUSION_MAP).sort((a, b) => b.length - a.length)
    for (const from of keys) {
      const tos = CONFUSION_MAP[from]
      for (const to of tos) {
        for (const replaced of applyConfusionOnce(s, from, to)) {
          if (forms.size < MAX_ALT_FORMS && !forms.has(replaced)) {
            forms.add(replaced)
            expand(replaced, depth + 1)
          }
        }
      }
    }

    for (const ended of withEndingVariants(s)) {
      if (forms.size < MAX_ALT_FORMS && !forms.has(ended)) {
        forms.add(ended)
        if (ended !== s) expand(ended, depth + 1)
      }
    }
  }

  expand(input, 0)
  // Always attach ending variants of the seed even if expand hit the cap early
  for (const ended of withEndingVariants(input)) forms.add(ended)
  return forms
}

/** Suffixes that are spelling noise, not real extra morphology (poshatu + n). */
function isNearExactRomanSuffix(suf) {
  if (!suf) return false
  return /^(n|m|ng|a|aa|i|ii|u|uu|un|um|e|o|h)$/i.test(suf)
}

/**
 * All roman strings to try against the Apple lexicon for this input.
 * Scalable fuzzy match — no per-word baking.
 */
function expandRomanQueries(input) {
  const q = new Set()
  const lower = input.toLowerCase()
  q.add(lower)
  q.add(input)
  for (const form of generateAlternateForms(lower)) {
    q.add(form)
    for (const ended of withEndingVariants(form)) q.add(ended)
  }
  return q
}

function getEnvBool(env, key, fallback) {
  try {
    if (env && env.engine && env.engine.schema && env.engine.schema.config) {
      const config = env.engine.schema.config
      if (typeof config.get_bool === 'function') {
        return config.get_bool(key) ?? fallback
      }
      if (typeof config.getBool === 'function') {
        return config.getBool(key) ?? fallback
      }
    }
  } catch (e) {
    return fallback
  }
  return fallback
}

function getEnvNumber(env, key, fallback) {
  try {
    if (env && env.engine && env.engine.schema && env.engine.schema.config) {
      const config = env.engine.schema.config
      if (typeof config.get_double === 'function') {
        const value = config.get_double(key)
        return Number.isFinite(value) ? value : fallback
      }
      if (typeof config.getDouble === 'function') {
        const value = config.getDouble(key)
        return Number.isFinite(value) ? value : fallback
      }
    }
  } catch (e) {
    return fallback
  }
  return fallback
}

function scoreCandidate(text, prevWord, isPhonetic, env) {
  const cacheKey = text + '|' + prevWord + '|' + (isPhonetic ? '1' : '0')
  const cached = cachedScore(cacheKey)
  if (cached !== null) return cached

  const unigramCount = UNIGRAM_LM.map.get(text) || 0
  const bigramCount = prevWord ? (BIGRAM_LM.map.get(prevWord + '|' + text) || 0) : 0
  const userCount = USER_LM.wordCounts.get(text) || 0
  const userBigram = prevWord ? (USER_LM.bigramCounts.get(prevWord + '|' + text) || 0) : 0
  // Do not boost pure phonetic forms — lexicon exact should win (macOS-like).
  const unigramScore = normalizedScore(unigramCount, UNIGRAM_LM.max) * LM_WEIGHTS.unigram
  const bigramScore = normalizedScore(bigramCount, BIGRAM_LM.max) * LM_WEIGHTS.bigram
  const userScore = userBoost(userCount + userBigram)
  const phoneticPenalty = isPhonetic ? -0.15 : 0
  const total = unigramScore + bigramScore + userScore + phoneticPenalty
  setCachedScore(cacheKey, total)
  return total
}

function scoreCandidateWithContext(text, prevWords, isPhonetic) {
  const prevWord = prevWords.length >= 1 ? prevWords[prevWords.length - 1] : ''
  const prev2 = prevWords.length >= 2 ? prevWords[prevWords.length - 2] : ''
  const unigramCount = UNIGRAM_LM.map.get(text) || 0
  const bigramCount = prevWord ? (BIGRAM_LM.map.get(prevWord + '|' + text) || 0) : 0
  const trigramCount = prev2 && prevWord ? (TRIGRAM_LM.map.get(prev2 + '|' + prevWord + '|' + text) || 0) : 0
  const userCount = USER_LM.wordCounts.get(text) || 0
  const userBigram = prevWord ? (USER_LM.bigramCounts.get(prevWord + '|' + text) || 0) : 0
  const unigramScore = normalizedScore(unigramCount, UNIGRAM_LM.max) * LM_WEIGHTS.unigram
  const bigramScore = normalizedScore(bigramCount, BIGRAM_LM.max) * LM_WEIGHTS.bigram
  const trigramScore = normalizedScore(trigramCount, TRIGRAM_LM.max) * TRIGRAM_WEIGHT
  const userScore = userBoost(userCount + userBigram)
  const phoneticPenalty = isPhonetic ? -0.15 : 0
  return unigramScore + bigramScore + trigramScore + userScore + phoneticPenalty
}

function recordUserChoice(path, word, prevWord, enableUserLm) {
  if (!enableUserLm || !word) return
  ensureUserLM(path)
  const nextWordCount = (USER_LM.wordCounts.get(word) || 0) + 1
  USER_LM.wordCounts.set(word, nextWordCount)
  if (prevWord) {
    const key = prevWord + '|' + word
    const nextBigramCount = (USER_LM.bigramCounts.get(key) || 0) + 1
    USER_LM.bigramCounts.set(key, nextBigramCount)
  }
  USER_LM_DIRTY = true
  USER_LM_PENDING_WRITES += 1
  if (USER_LM_PENDING_WRITES >= USER_FLUSH_THRESHOLD) {
    const resolvedPath = resolveUserPath(path)
    writeUserLM(resolvedPath, USER_LM.wordCounts, USER_LM.bigramCounts)
    USER_LM_DIRTY = false
    USER_LM_PENDING_WRITES = 0
  }
}


// ---------------------------------------------------------------------------
// Local ONNX ranker client (Unix socket via external helper)
// Never blocks typing: timeout / failure falls back to n-gram scores.
// ---------------------------------------------------------------------------

const ONNX_DEFAULT_SOCK = '~/Library/Rime/run/gu_ranker.sock'
const ONNX_CACHE = new Map()
const ONNX_CACHE_LIMIT = 400

function onnxCacheGet(key) {
  if (!ONNX_CACHE.has(key)) return null
  return ONNX_CACHE.get(key)
}

function onnxCacheSet(key, value) {
  if (ONNX_CACHE.size >= ONNX_CACHE_LIMIT) {
    const first = ONNX_CACHE.keys().next().value
    ONNX_CACHE.delete(first)
  }
  ONNX_CACHE.set(key, value)
}

function rankWithOnnx(input, candTexts, prev, env) {
  const enable = getEnvBool(env, 'translator/onnx_enable', true)
  if (!enable || !candTexts || candTexts.length === 0) return null
  const cacheKey = input + '||' + prev + '||' + candTexts.join('\u0001')
  const cached = onnxCacheGet(cacheKey)
  if (cached) return cached

  // librime-qjs may expose system() or not; try best-effort helper CLI.
  const helper = getEnvString(env, 'translator/onnx_helper', resolveUserPath('~/Library/Rime/run/gu_ranker_client'))
  const sock = resolveUserPath(getEnvString(env, 'translator/onnx_socket', ONNX_DEFAULT_SOCK))
  const timeoutMs = getEnvNumber(env, 'translator/onnx_timeout_ms', 3)
  if (typeof system !== 'function' && typeof os === 'undefined') {
    return null
  }

  const payload = JSON.stringify({ input: input, cands: candTexts, prev: prev || '', timeout_ms: timeoutMs })
  // Write temp request via helper stdin protocol: gu_ranker_client --sock PATH --json PAYLOAD
  try {
    let out = null
    if (typeof system === 'function') {
      // system() returns exit code only in many embeds; prefer os.exec if present
      out = null
    }
    if (typeof os !== 'undefined' && typeof os.exec === 'function') {
      // QuickJS os.exec is not always available; skip
      out = null
    }
    // Pipe through a tiny sync helper that prints JSON scores
    if (typeof std !== 'undefined' && std.popen) {
      const cmd = helper + ' --sock ' + JSON.stringify(sock) + ' --stdin'
      const pipe = std.popen(cmd, 'w+')
      if (pipe) {
        pipe.puts(payload)
        pipe.close(false) // keep read side? depends on impl
      }
    }
    // Fallback: look for precomputed scores file written by sidecar watcher (optional)
    const scorePath = resolveUserPath('~/Library/Rime/run/last_scores.json')
    // Direct TCP/unix not available in qjs sandbox — call helper that reads argv
    if (typeof std !== 'undefined' && std.popen) {
      const escaped = payload.replace(/'/g, "'\\''")
      const cmd = helper + ' --sock ' + sock + " --json '" + escaped + "'"
      const pipe = std.popen(cmd, 'r')
      if (pipe) {
        out = pipe.readAsString()
        pipe.close()
      }
    }
    if (!out) return null
    const parsed = JSON.parse(out)
    const scores = parsed.scores || parsed
    if (!Array.isArray(scores) || scores.length !== candTexts.length) return null
    onnxCacheSet(cacheKey, scores)
    return scores
  } catch (e) {
    return null
  }
}

function getEnvString(env, key, fallback) {
  try {
    if (env && env.engine && env.engine.schema && env.engine.schema.config) {
      const config = env.engine.schema.config
      if (typeof config.get_string === 'function') {
        return config.get_string(key) || fallback
      }
      if (typeof config.getString === 'function') {
        return config.getString(key) || fallback
      }
    }
  } catch (e) {
    return fallback
  }
  return fallback
}


// ---------------------------------------------------------------------------
// Rime Translator
// ---------------------------------------------------------------------------

/**
 * @implements {Translator}
 */
export class GujaratiTranslator {
  constructor(env) {
    console.log('$qjs$ gujarati translator init')
    loadLexiconBlob(env)
    loadLanguageModels(env)
  }

  finalizer() {
    console.log('$qjs$ gujarati translator finit')
  }

  /**
   * @param {string} input
   * @param {Segment} segment
   * @param {Environment} env
   * @returns {Array<Candidate>}
   */
  translate(input, segment, env) {
    try {
      if (!input || input.length === 0) {
        return []
      }

      loadLexiconBlob(env)
      loadLanguageModels(env)

      const enableUserLm = getEnvBool(env, 'translator/enable_user_lm', true)
      const hardGate = getEnvBool(env, 'translator/lexicon_hard_gate', true)
      const includeLatin = getEnvBool(env, 'translator/include_latin', true)
      const maxPrefix = Math.max(0, Math.floor(getEnvNumber(env, 'translator/max_prefix', 6)))
      const maxPhonetic = Math.max(0, Math.floor(getEnvNumber(env, 'translator/max_phonetic', 5)))
      LM_WEIGHTS.unigram = getEnvNumber(env, 'translator/lm_unigram_weight', LM_WEIGHTS.unigram)
      LM_WEIGHTS.bigram = getEnvNumber(env, 'translator/lm_bigram_weight', LM_WEIGHTS.bigram)
      LM_WEIGHTS.user = getEnvNumber(env, 'translator/lm_user_weight', LM_WEIGHTS.user)
      TRIGRAM_WEIGHT = getEnvNumber(env, 'translator/lm_trigram_weight', TRIGRAM_WEIGHT)
      const prevWords = getContextPrevWords(env)
      const prevWord = prevWords.length > 0 ? prevWords[prevWords.length - 1] : ''
      const lower = input.toLowerCase()
      const seen = new Set()
      const items = []

      function pushCand(text, comment, quality, tier, isPhonetic, romanKey) {
        if (!text || seen.has(text)) return false
        seen.add(text)
        const cand = new Candidate('gujarati', segment.start, segment.end, text, comment || '', quality)
        cand.quality = quality
        items.push({
          candidate: cand,
          tier,
          isPhonetic: !!isPhonetic,
          romanKey: romanKey || lower,
          weight: lexiconWeight(romanKey || lower),
        })
        return true
      }

      // GENERAL fuzzy lexicon lookup: expand roman confusions/endings, then hit 96k Apple dict.
      // poshatu → poshatun → પોષતું; ketli → keTlii → (phonetic) કેટલી + unigram boost.
      const romanQueries = expandRomanQueries(input)
      const altForms = generateAlternateForms(lower)

      const exc = APPLE_EXCEPTIONS.get(lower) || APPLE_EXCEPTIONS.get(input)
      if (exc) {
        pushCand(exc, input, 999, TIER_EXACT, false, lower)
      }

      const exactHits = []
      for (const q of romanQueries) {
        const word = APPLE_LEXICON.get(q) || DICT_TRIE.findExact(q)
        if (!word) continue
        exactHits.push({ roman: q, word, weight: Math.max(lexiconWeight(q), q === lower ? 1 : 0) })
      }
      exactHits.sort((a, b) => b.weight - a.weight || a.roman.length - b.roman.length)
      for (const hit of exactHits) {
        const q = hit.roman === lower ? 950 : 880
        pushCand(hit.word, hit.roman === lower ? input : hit.roman, q + Math.min(40, Math.log1p(hit.weight) * 5), TIER_EXACT, false, hit.roman)
      }

      // Near-exact lexicon: typed roman is a prefix of a lexicon key by only n/m/… (poshatu→poshatun)
      for (const seed of romanQueries) {
        if (seed.length < 2) continue
        for (const entry of DICT_TRIE.findPrefixEntries(seed, 12)) {
          if (!entry || !entry.value) continue
          if (!entry.key.startsWith(seed)) continue
          const suf = entry.key.slice(seed.length)
          if (!isNearExactRomanSuffix(suf)) continue
          const w = lexiconWeight(entry.key)
          pushCand(entry.value, input, 900 + Math.min(50, Math.log1p(w) * 6), TIER_EXACT, false, entry.key)
        }
      }

      const exactCount = items.filter((x) => x.tier === TIER_EXACT).length

      // Latin only after we know exact/dict tiers will sort above it
      if (includeLatin) {
        pushCand(input, '', 400, TIER_LATIN, false, lower)
      }

      // Generate phonetics, then RESCORE with native wordlist/stems (IndicXlit-style).
      // This is what makes favshe → ફાવશે win without baking that pair.
      const phoneticForms = []
      const gujarati = transliterate(input)
      if (gujarati && gujarati !== input) phoneticForms.push(gujarati)
      for (const form of altForms) {
        if (form.toLowerCase() === lower) continue
        const altGu = transliterate(form)
        if (altGu && altGu !== form && altGu !== gujarati) phoneticForms.push(altGu)
      }

      const phonScored = []
      for (const text of phoneticForms) {
        if (seen.has(text)) continue
        const known = KNOWN_WORDS.has(text)
        if (hardGate && exactCount > 0 && !known) continue
        const validity = dictionaryValidity(text)
        phonScored.push({ text, known, validity })
      }
      phonScored.sort((a, b) => {
        if (a.validity.attested !== b.validity.attested) return a.validity.attested ? -1 : 1
        if (b.validity.score !== a.validity.score) return b.validity.score - a.validity.score
        return 0
      })

      let phoneticAdded = 0
      for (const item of phonScored) {
        if (phoneticAdded >= maxPhonetic) break
        const tier = item.validity.attested ? TIER_DICT : TIER_PHONETIC
        const q = item.validity.attested
          ? 700 + Math.min(99, item.validity.score * 12)
          : (item.known ? 300 : 200)
        if (pushCand(item.text, input, q, tier, true, lower)) phoneticAdded += 1
      }

      if (exactCount === 0 && phoneticAdded === 0 && gujarati && gujarati !== input) {
        const v = dictionaryValidity(gujarati)
        pushCand(gujarati, input, v.attested ? 720 : 250, v.attested ? TIER_DICT : TIER_PHONETIC, true, lower)
      }

      if (input.length >= 2 && maxPrefix > 0) {
        // Also probe fuzzy roman prefixes (poShatu… / poshatu…)
        const prefixSeeds = new Set([lower])
        for (const q of romanQueries) {
          if (q.length >= 2) prefixSeeds.add(q)
        }
        const prefixEntries = []
        for (const seed of prefixSeeds) {
          for (const entry of DICT_TRIE.findPrefixEntries(seed, Math.max(maxPrefix * 3, 16))) {
            prefixEntries.push(entry)
          }
        }
        prefixEntries.sort((a, b) => lexiconWeight(b.key) - lexiconWeight(a.key))
        let prefixAdded = 0
        for (const entry of prefixEntries) {
          if (prefixAdded >= maxPrefix) break
          if (!entry || !entry.value) continue
          if (seen.has(entry.value)) continue
          // Find how this entry relates to the typed input
          let suffix = ''
          if (entry.key.startsWith(lower)) suffix = entry.key.slice(lower.length)
          else {
            // fuzzy seed longer/shorter — treat as near-exact if edit is tiny
            suffix = entry.key.length > lower.length ? entry.key.slice(lower.length) : ''
          }
          const w = lexiconWeight(entry.key)
          // poshatu + n → પોષતું should rank as dictionary hit, not buried ~n prefix
          if (entry.key.startsWith(lower) && isNearExactRomanSuffix(suffix)) {
            if (pushCand(entry.value, input, 860 + Math.min(40, Math.log1p(w) * 5), TIER_EXACT, false, entry.key)) {
              prefixAdded += 1
            }
            continue
          }
          if (entry.key === lower) continue
          const comment = suffix ? ('~' + suffix) : input
          if (pushCand(entry.value, comment, 80 + Math.min(40, Math.log1p(w) * 5), TIER_PREFIX, false, entry.key)) {
            prefixAdded += 1
          }
        }
      }

      if (items.length === 0) return []

      const scored = items.map((item, index) => {
        const lm = scoreCandidateWithContext(item.candidate.text, prevWords, item.isPhonetic)
        const freq = Math.log1p(item.weight || 0) * 0.35
        const validity = dictionaryValidity(item.candidate.text)
        const dictBoost = validity.attested ? validity.score * 1.4 : 0
        return { ...item, score: lm + freq + dictBoost, validity, index }
      })

      const topForOnnx = scored
        .slice()
        .sort((a, b) => (a.tier !== b.tier ? a.tier - b.tier : b.score - a.score))
        .slice(0, 8)
      const onnxScores = rankWithOnnx(
        lower,
        topForOnnx.map((x) => x.candidate.text),
        prevWord,
        env
      )
      if (onnxScores) {
        const onnxWeight = getEnvNumber(env, 'translator/onnx_weight', 1.2)
        for (let i = 0; i < topForOnnx.length; i++) {
          topForOnnx[i].score += onnxWeight * Number(onnxScores[i] || 0)
        }
      }

      scored.sort((a, b) => {
        if (a.tier !== b.tier) return a.tier - b.tier
        if (b.score !== a.score) return b.score - a.score
        if ((b.weight || 0) !== (a.weight || 0)) return (b.weight || 0) - (a.weight || 0)
        return a.index - b.index
      })

      const sortedCandidates = scored.map((item, rank) => {
        const c = item.candidate
        c.quality = (4 - item.tier) * 200 + Math.max(0, 180 - rank)
        return c
      })

      if (sortedCandidates.length > 0) {
        const learn = sortedCandidates.find((c) => c.text !== input) || sortedCandidates[0]
        recordUserChoice(USER_LM_DEFAULT_PATH, learn.text, prevWord, enableUserLm)
      }

      return sortedCandidates
    } catch (e) {
      console.error('$qjs$ translate error:', e.message)
      return []
    }
  }
}
