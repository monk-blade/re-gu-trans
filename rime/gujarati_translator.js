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

// Candidate tiers — primary sort key (lower = better).
const TIER_EXACT = 0
const TIER_DICT = 1   // phonetic form attested via native wordlist / stem (macOS-like)
const TIER_PHONETIC = 2
const TIER_LATIN = 3  // echo latin below script phonetics (Google/Apple-like)
const TIER_PREFIX = 4
const TIER_EMOJI = 5  // keyword emoji; always below script candidates
const TIER_MAX = 5

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

// Keep in sync with scripts/build_gu_word_freq.py SUFFIXES
const GU_SUFFIXES = [
  'વાળાઓ', 'વાળીઓ', 'વાળું', 'વાળી', 'વાળા', 'વાળો',
  'ીઓ', 'ાઓ', 'ોને', 'ાને', 'ીને', 'ુંને',
  'માંથી', 'માં', 'થી', 'ની', 'નો', 'ના', 'ને', 'નું', 'નાં',
  'શે', 'શો', 'શું', 'ીશ', 'ીશું',
  '્યો', '્યા', '્યું',
  'તો', 'તા', 'તી', 'તું', 'તાં',
  'વું', 'વા', 'વાનું', 'વાની', 'વાના',
  'ે', 'ો', 'ા', 'ી', 'ું', 'ાં',
]

const ATTESTED = new Set()
let ATTESTED_FLOOR = 50

// roman keyword / native GU word → [{e, w}, ...]
const EMOJI_BY_ROMAN = new Map()
const EMOJI_BY_NATIVE = new Map()
let EMOJI_LOADED = false

function rememberEmoji(map, key, emoji, weight) {
  if (!key || !emoji) return
  let list = map.get(key)
  if (!list) {
    list = []
    map.set(key, list)
  }
  for (const it of list) {
    if (it.e === emoji) {
      if (weight > it.w) it.w = weight
      return
    }
  }
  list.push({ e: emoji, w: weight })
  list.sort((a, b) => b.w - a.w)
}

function loadEmojiKeywords(env) {
  if (EMOJI_LOADED) return
  EMOJI_LOADED = true
  const paths = []
  if (env && env.userDataDir) {
    paths.push(env.userDataDir + '/js/emoji_keywords.json')
    paths.push(env.userDataDir + '/emoji_keywords.json')
  }
  paths.push(resolveUserPath('~/Library/Rime/js/emoji_keywords.json'))
  paths.push(resolveUserPath('~/Library/Rime/emoji_keywords.json'))

  let text = null
  for (const p of paths) {
    text = loadTextViaEnv(env, p)
    if (text) break
  }
  if (!text) {
    console.log('$qjs$ emoji keywords missing')
    return
  }
  try {
    const data = JSON.parse(text)
    EMOJI_BY_ROMAN.clear()
    EMOJI_BY_NATIVE.clear()
    for (const [code, items] of Object.entries(data || {})) {
      const roman = String(code || '').toLowerCase()
      if (!roman || !Array.isArray(items)) continue
      for (const it of items) {
        const emoji = it && (it.e || it.emoji || it[0])
        const weight = Number((it && (it.w || it.weight || it[1])) || 100)
        if (!emoji) continue
        rememberEmoji(EMOJI_BY_ROMAN, roman, String(emoji), Number.isFinite(weight) ? weight : 100)
        // Reverse-index via Apple lexicon so native candidates also surface emoji
        const native = APPLE_LEXICON.get(roman)
        if (native) {
          rememberEmoji(EMOJI_BY_NATIVE, native, String(emoji), Number.isFinite(weight) ? weight : 100)
        }
      }
    }
    console.log(
      '$qjs$ emoji loaded romans=' + EMOJI_BY_ROMAN.size + ' natives=' + EMOJI_BY_NATIVE.size
    )
  } catch (e) {
    console.error('$qjs$ emoji parse error:', e.message)
  }
}

function loadLanguageModels(env) {
  if (LM_LOADED) return
  LM_LOADED = true
  const uniPaths = []
  const stemPaths = []
  const attestedPaths = []
  if (env && env.userDataDir) {
    uniPaths.push(env.userDataDir + '/js/lm/unigram.tsv')
    uniPaths.push(env.userDataDir + '/lm/unigram.tsv')
    stemPaths.push(env.userDataDir + '/js/lm/stems.json')
    stemPaths.push(env.userDataDir + '/lm/stems.json')
    attestedPaths.push(env.userDataDir + '/js/lm/attested.json')
    attestedPaths.push(env.userDataDir + '/lm/attested.json')
  }
  uniPaths.push(resolveUserPath('~/Library/Rime/js/lm/unigram.tsv'))
  uniPaths.push(resolveUserPath('~/Library/Rime/lm/unigram.tsv'))
  stemPaths.push(resolveUserPath('~/Library/Rime/js/lm/stems.json'))
  attestedPaths.push(resolveUserPath('~/Library/Rime/js/lm/attested.json'))
  attestedPaths.push(resolveUserPath('~/Library/Rime/lm/attested.json'))

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

  let attestedText = null
  for (const p of attestedPaths) {
    attestedText = loadTextViaEnv(env, p)
    if (attestedText) break
  }
  if (attestedText) {
    try {
      const data = JSON.parse(attestedText)
      ATTESTED.clear()
      const words = data.words || data || []
      if (Array.isArray(words)) {
        for (const w of words) {
          if (w) ATTESTED.add(String(w))
        }
      } else if (words && typeof words === 'object') {
        for (const w of Object.keys(words)) ATTESTED.add(w)
      }
      if (Number.isFinite(Number(data.floor))) ATTESTED_FLOOR = Number(data.floor)
      console.log('$qjs$ attested loaded entries=' + ATTESTED.size + ' floor=' + ATTESTED_FLOOR)
    } catch (e) {
      console.error('$qjs$ attested parse error:', e.message)
    }
  } else {
    console.log('$qjs$ attested missing')
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

/** Native-dict / stem / spell-dict validity — IndicXlit-style rescoring signal. */
function dictionaryValidity(text) {
  if (!text) return { score: 0, attested: false, evidence: 0, spellOk: false }
  const uni = UNIGRAM_LM.map.get(text) || 0
  const spellOk = ATTESTED.has(text)
  let spellHit = spellOk ? ATTESTED_FLOOR : 0
  let stemHit = STEM_FREQ.get(text) || 0
  if (ATTESTED.has(text)) stemHit = Math.max(stemHit, ATTESTED_FLOOR)
  for (const suf of GU_SUFFIXES) {
    if (text.length <= suf.length + 1) continue
    if (!text.endsWith(suf)) continue
    const stem = text.slice(0, -suf.length)
    if (!stem) continue
    stemHit = Math.max(stemHit, STEM_FREQ.get(stem) || 0)
    if (ATTESTED.has(stem)) stemHit = Math.max(stemHit, ATTESTED_FLOOR)
    // attested conjugations of the same stem (ફાવે / ફાવો / ફાવવું)
    for (const ext of ['ે', 'ો', 'ા', 'ી', 'ું', 'વું', 'તું', 'વા', 'શે', 'શો']) {
      const form = stem + ext
      stemHit = Math.max(stemHit, UNIGRAM_LM.map.get(form) || 0, STEM_FREQ.get(form) || 0)
      if (ATTESTED.has(form)) stemHit = Math.max(stemHit, ATTESTED_FLOOR)
    }
  }
  const evidence = Math.max(uni, stemHit, spellHit)
  // Penalize awkward virama clusters for pure inventions
  let virama = 0
  for (const ch of text) if (ch === '\u0ACD') virama += 1
  const viramaPenalty = virama * 0.25
  // Prefer full-word unigram over stem-only (વિકસ stem must not beat વિકાસ uni).
  const score =
    Math.log1p(uni) +
    Math.log1p(spellHit) * 0.35 +
    Math.log1p(stemHit) * (uni > 0 ? 0.35 : 0.7) -
    viramaPenalty
  return {
    score: Math.max(0, score),
    attested: evidence > 0 || spellOk,
    evidence,
    spellOk,
  }
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

/**
 * Productive conjunct pairs (C1,C2) — Apple / Google Indic / MS phonetic style.
 * Default between consonants is inherent schwa (no virama); only these form clusters.
 * Explicit virama remains available via '+' in the roman input.
 */
const PRODUCTIVE_CONJUNCTS = new Set([
  // ya-phala (વ્ય, ક્ય, …) — past participles, passives
  'v|y', 'k|y', 'g|y', 'c|y', 'ch|y', 'j|y', 't|y', 'd|y', 'n|y', 'p|y', 'b|y',
  'm|y', 'r|y', 'l|y', 's|y', 'sh|y', 'h|y', 'T|y', 'D|y',
  // ra clusters
  'p|r', 't|r', 'k|r', 'g|r', 'd|r', 'b|r', 's|r', 'sh|y', 'sh|r', 'f|r', 'ph|r',
  // va clusters
  'k|v', 't|v', 'd|v', 's|v', 'n|v', 'dh|v',
  // misc common
  't|n', 's|n', 's|t', 's|k',
])

function conjunctKey(a, b) {
  return a + '|' + b
}

function shouldFormConjunct(leftTok, rightTok) {
  if (!leftTok || !rightTok) return false
  if (PRODUCTIVE_CONJUNCTS.has(conjunctKey(leftTok, rightTok))) return true
  // already-atomic digraphs in CONSONANTS (ksh/gy/dv) are single tokens
  return false
}

const ANUSVARA = '\u0A82'
const U_MATRA = '\u0AC1'
const UU_MATRA = '\u0AC2'

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
      // Indic IME grammar: default inherent schwa between consonants.
      // Virama only for explicit '+' or productive conjuncts (vy, pr, tr, …).
      if (nextToken === '+') {
        result += consChar + VIRAMA
      } else if (
        nextToken !== undefined &&
        CONSONANTS[nextToken] !== undefined &&
        shouldFormConjunct(token, nextToken)
      ) {
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

/** Past-participle / nasal final -u (પોષતું, પરખાવ્યું) — Google/Apple often omit 'n'/'m'. */
function withNasalFinalU(gu) {
  if (!gu) return null
  if (gu.endsWith(U_MATRA + ANUSVARA) || gu.endsWith(UU_MATRA + ANUSVARA)) return null
  if (gu.endsWith(U_MATRA)) return gu + ANUSVARA
  return null
}

function transliterate(input) {
  const tokens = tokenize(input)
  return transliterateTokens(tokens)
}

/**
 * Apple/Google-style diphthong splits: roman `ai`/`ay`/`oi`/`ui`/`ei` often mean
 * independent ઈ/ઇ (કોઈ, જોઈ, થઈ) — not only matra ૈ / bare ી from i↔ii.
 * Constructs forms the matra transliterator cannot emit.
 */
function diphthongAlternateForms(roman) {
  const out = []
  if (!roman) return out
  const s = String(roman).toLowerCase()
  const digraphs = ['ai', 'ay', 'oi', 'ui', 'ei']
  for (const digraph of digraphs) {
    let idx = 0
    let added = 0
    while (idx <= s.length - digraph.length && added < 3) {
      const at = s.indexOf(digraph, idx)
      if (at < 0) break
      const prefix = s.slice(0, at)
      const suffix = s.slice(at + digraph.length)
      // Avoid splitting inside longer vowel runs (e.g. aai already has aa+i path).
      if (at > 0 && s[at - 1] === 'a' && digraph === 'ai') {
        idx = at + 1
        continue
      }
      const prefixGu = prefix ? transliterate(prefix) : ''
      const suffixGu = suffix ? transliterate(suffix) : ''
      const nuclei = []
      if (digraph === 'ai') {
        if (!prefixGu) {
          nuclei.push('ઐ', 'અઈ', 'અઇ', 'આઈ', 'આઇ')
        } else if (endsWithConsonantWithImplicitA(prefixGu)) {
          // gai→ગઈ/ગઇ; also aa-colored ગાઈ/ગાઇ (Apple shows both)
          nuclei.push(prefixGu + 'ઈ', prefixGu + 'ઇ')
          const withAa = prefixGu.slice(0, -1) + prefixGu.slice(-1) + VOWEL_MATRAS.aa
          nuclei.push(withAa + 'ઈ', withAa + 'ઇ')
        }
      } else if (digraph === 'ay') {
        if (!prefixGu) {
          nuclei.push('અય', 'આય')
        } else if (endsWithConsonantWithImplicitA(prefixGu)) {
          nuclei.push(prefixGu + 'ય')
          const withAa = prefixGu.slice(0, -1) + prefixGu.slice(-1) + VOWEL_MATRAS.aa
          nuclei.push(withAa + 'ય')
        }
      } else if (digraph === 'oi' || digraph === 'ui' || digraph === 'ei') {
        // joi→જોઈ, kui→કુઈ, udhei→ઉધેઈ — vowel matra + independent ઈ/ઇ
        if (endsWithConsonantWithImplicitA(prefixGu)) {
          const matraKey = digraph === 'oi' ? 'o' : digraph === 'ui' ? 'u' : 'e'
          const withMatra = prefixGu.slice(0, -1) + prefixGu.slice(-1) + VOWEL_MATRAS[matraKey]
          nuclei.push(withMatra + 'ઈ', withMatra + 'ઇ')
          if (digraph === 'ui') {
            const withUu = prefixGu.slice(0, -1) + prefixGu.slice(-1) + VOWEL_MATRAS.uu
            nuclei.push(withUu + 'ઈ', withUu + 'ઇ')
          }
        }
      }
      for (const n of nuclei) out.push(n + suffixGu)
      if (nuclei.length) added += 1
      idx = at + 1
    }
  }
  return out
}

/** All phonetic script forms to consider for one roman string (base + nasal -u + diphthongs). */
function phoneticFormsForRoman(roman) {
  const out = []
  const seen = new Set()
  function add(g) {
    if (!g || g === roman || seen.has(g)) return
    seen.add(g)
    out.push(g)
  }
  const base = transliterate(roman)
  add(base)
  add(withNasalFinalU(base))
  for (const g of diphthongAlternateForms(roman)) {
    add(g)
    add(withNasalFinalU(g))
  }
  return out
}

// ---------------------------------------------------------------------------
// Phonetic alternate form generator
// Generates alternate spellings by inserting implicit 'a' between
// consecutive consonant characters, handling variations like
// nmste → namste → namaste for dictionary lookup.
// ---------------------------------------------------------------------------

const MAX_ALT_FORMS = 96
const MAX_ALT_INSERTIONS = 2

// Phonetic confusions users actually type (macOS fuzzy mapping).
// sh↔Sh covers પોશ vs પોષ; t↔T covers કેત vs કેટ; f↔ph; endings cover િ vs ી, u vs ું.
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
  'f': ['ph'],
  'ph': ['f'],
  // Apple/Google treat w as વ (vikas↔wikas)
  'v': ['w'],
  'w': ['v'],
  // Colloquial z↔j (zindabad / jindabad)
  'z': ['j'],
  'j': ['z'],
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

/** True when roman `i`/`ii`/`ee` at `iPos` is the second half of ai/oi/ui/ei (not ketli-style). */
function isDiphthongI(s, iPos) {
  if (!s || iPos <= 0) return false
  const prev = s[iPos - 1]
  return prev === 'a' || prev === 'e' || prev === 'o' || prev === 'u'
}

/** Extra roman queries for lexicon lookup (poshatu ↔ poshatun, ketli ↔ keTlii). */
function withEndingVariants(s) {
  const out = new Set([s])
  for (const [from, tos] of Object.entries(ENDING_VARIANTS)) {
    if (s.length <= from.length) continue
    if (!s.endsWith(from)) continue
    // gai→gaee/gaii would invent ગી and outrank attested ગઈ; keep i↔ii for consonant+i only.
    if ((from === 'i' || from === 'ii' || from === 'ee') && isDiphthongI(s, s.length - from.length)) {
      continue
    }
    const stem = s.slice(0, -from.length)
    for (const to of tos) out.add(stem + to)
  }
  return out
}

/** Mid-string vowel length variants (bounded) — i↔ii, a↔aa. */
function withMidVowelVariants(s) {
  const out = new Set([s])
  if (!s || s.length < 3) return out
  const pairs = [
    ['i', 'ii'],
    ['ii', 'i'],
    ['a', 'aa'],
    ['aa', 'a'],
  ]
  for (const [from, to] of pairs) {
    let idx = 0
    let added = 0
    while (idx <= s.length - from.length && added < 4) {
      const at = s.indexOf(from, idx)
      if (at < 0) break
      // Prefer interior / non-trivial positions; still allow endings
      if (at > 0) {
        // Skip ai→aii (and oi/ui/ei); diphthongs use split phonetics instead.
        if ((from === 'i' || from === 'ii') && isDiphthongI(s, at)) {
          idx = at + 1
          continue
        }
        out.add(s.slice(0, at) + to + s.slice(at + from.length))
        added += 1
      }
      idx = at + 1
    }
  }
  return out
}

/** Leading a↔aa (avo→aavo→આવો). Mid-vowel pass skips index 0. */
function withLeadingVowelVariants(s) {
  const out = new Set([s])
  if (!s || s.length < 2) return out
  if (s.startsWith('aa')) out.add('a' + s.slice(2))
  else if (s.startsWith('a') && s[1] !== 'a') out.add('aa' + s.slice(1))
  return out
}

/** Optional final schwa letter for soft lexicon keys (vikas→vikasa). */
function withTrailingSchwa(s) {
  const out = new Set([s])
  if (!s || s.length < 3) return out
  const last = s[s.length - 1]
  if (last in CONSONANTS) out.add(s + 'a')
  return out
}

/** After retroflex T/Th/D/Dh, dental n is often typed for ણ (gothni→gothaNi). */
function withRetroflexNasal(s) {
  const out = new Set([s])
  if (!s || s.length < 2) return out
  const keys = ['Th', 'Dh', 'T', 'D']
  for (const stem of keys) {
    let idx = 0
    while (idx <= s.length - stem.length - 1) {
      const at = s.indexOf(stem, idx)
      if (at < 0) break
      const nPos = at + stem.length
      if (nPos < s.length && s[nPos] === 'n') {
        out.add(s.slice(0, nPos) + 'N' + s.slice(nPos + 1))
      }
      idx = at + 1
    }
  }
  return out
}

/** Homorganic / simplified anusvara: n|m before stop → M (ં). ISO 15919 / ITRANS. */
const ANUSVARA_STOPS = [
  'kh', 'gh', 'chh', 'ch', 'jh', 'Th', 'th', 'Dh', 'dh', 'ph', 'bh',
  'k', 'g', 'c', 'j', 'T', 't', 'D', 'd', 'p', 'b',
]

function withAnusvaraNasals(s) {
  const out = new Set([s])
  if (!s) return out
  for (const nasal of ['n', 'm']) {
    let idx = 0
    while (idx < s.length) {
      const at = s.indexOf(nasal, idx)
      if (at < 0) break
      const rest = s.slice(at + 1)
      for (const stop of ANUSVARA_STOPS) {
        if (rest.startsWith(stop)) {
          out.add(s.slice(0, at) + 'M' + rest)
          break
        }
      }
      idx = at + 1
    }
  }
  return out
}

/** Geminate doubles → explicit virama (himmat→him+mat→હિમ્મત). */
function withGeminates(s) {
  const out = new Set([s])
  if (!s || s.length < 2) return out
  const doubles = ['mm', 'nn', 'tt', 'kk', 'll', 'pp', 'bb', 'dd', 'gg', 'jj', 'ss']
  for (const d of doubles) {
    let idx = 0
    while (idx <= s.length - 2) {
      const at = s.indexOf(d, idx)
      if (at < 0) break
      out.add(s.slice(0, at) + d[0] + '+' + d[1] + s.slice(at + 2))
      idx = at + 1
    }
  }
  return out
}

/** Bounded English-loan digraph rewrites (gated). */
const ENABLE_LOAN_DIGRAPHS = true

function withLoanDigraphs(s) {
  const out = new Set([s])
  if (!ENABLE_LOAN_DIGRAPHS || !s) return out
  const lower = s.toLowerCase()
  // Only rewrite clearly Latin-looking tokens (avoid mane→man, kyare→kayar).
  if (!/(sch|tion|qu|ck|oo|ee|school|college|doctor|hospital|london)/.test(lower)) {
    return out
  }
  const reps = [
    ['sch', 'sk'],
    ['tion', 'shan'],
    ['qu', 'kv'],
    ['ck', 'k'],
    ['oo', 'uu'],
    ['ee', 'ii'],
  ]
  for (const [a, b] of reps) {
    let idx = 0
    while (idx <= lower.length - a.length) {
      const at = lower.indexOf(a, idx)
      if (at < 0) break
      out.add(lower.slice(0, at) + b + lower.slice(at + a.length))
      idx = at + 1
    }
  }
  if (lower.length >= 5 && lower.endsWith('e') && /[bcdfghjklmnpqrstvwxyz]/.test(lower[lower.length - 2])) {
    out.add(lower.slice(0, -1))
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

  // Prioritize seed ending + vowel-length + one-step confusions before deep recursion
  for (const ended of withEndingVariants(input)) forms.add(ended)
  for (const mid of withMidVowelVariants(input)) forms.add(mid)
  for (const lead of withLeadingVowelVariants(input)) forms.add(lead)
  for (const trail of withTrailingSchwa(input)) forms.add(trail)
  for (const ret of withRetroflexNasal(input)) forms.add(ret)
  for (const nas of withAnusvaraNasals(input)) forms.add(nas)
  for (const gem of withGeminates(input)) forms.add(gem)
  for (const loan of withLoanDigraphs(input)) forms.add(loan)
  const keysFirst = Object.keys(CONFUSION_MAP).sort((a, b) => b.length - a.length)
  for (const from of keysFirst) {
    for (const to of CONFUSION_MAP[from]) {
      for (const replaced of applyConfusionOnce(input, from, to)) {
        forms.add(replaced)
        for (const ended of withEndingVariants(replaced)) forms.add(ended)
        for (const mid of withMidVowelVariants(replaced)) forms.add(mid)
        for (const lead of withLeadingVowelVariants(replaced)) forms.add(lead)
        for (const trail of withTrailingSchwa(replaced)) forms.add(trail)
        for (const ret of withRetroflexNasal(replaced)) forms.add(ret)
        for (const nas of withAnusvaraNasals(replaced)) forms.add(nas)
        for (const gem of withGeminates(replaced)) forms.add(gem)
        for (const loan of withLoanDigraphs(replaced)) forms.add(loan)
        if (forms.size >= MAX_ALT_FORMS) break
      }
      if (forms.size >= MAX_ALT_FORMS) break
    }
    if (forms.size >= MAX_ALT_FORMS) break
  }

  function expand(s, depth) {
    if (depth >= MAX_ALT_INSERTIONS) return
    if (forms.size >= MAX_ALT_FORMS) return
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
    for (const mid of withMidVowelVariants(s)) {
      if (forms.size < MAX_ALT_FORMS && !forms.has(mid)) {
        forms.add(mid)
      }
    }
    for (const nas of withAnusvaraNasals(s)) {
      if (forms.size < MAX_ALT_FORMS && !forms.has(nas)) {
        forms.add(nas)
        if (nas !== s) expand(nas, depth + 1)
      }
    }
    for (const gem of withGeminates(s)) {
      if (forms.size < MAX_ALT_FORMS && !forms.has(gem)) forms.add(gem)
    }
  }

  expand(input, 0)
  for (const ended of withEndingVariants(input)) forms.add(ended)
  for (const mid of withMidVowelVariants(input)) forms.add(mid)
  for (const lead of withLeadingVowelVariants(input)) {
    forms.add(lead)
    for (const ended of withEndingVariants(lead)) forms.add(ended)
    for (const mid of withMidVowelVariants(lead)) forms.add(mid)
  }
  for (const ret of withRetroflexNasal(input)) {
    forms.add(ret)
    for (const ended of withEndingVariants(ret)) forms.add(ended)
  }
  for (const nas of withAnusvaraNasals(input)) {
    forms.add(nas)
    for (const mid of withMidVowelVariants(nas)) {
      forms.add(mid)
      for (const mid2 of withMidVowelVariants(mid)) forms.add(mid2)
    }
  }
  for (const gem of withGeminates(input)) forms.add(gem)
  for (const loan of withLoanDigraphs(input)) forms.add(loan)
  // Retroflex nasal on t→T confusions (gothni→goThni→goThNi)
  for (const form of Array.from(forms).slice(0, MAX_ALT_FORMS)) {
    for (const ret of withRetroflexNasal(form)) forms.add(ret)
    for (const nas of withAnusvaraNasals(form)) forms.add(nas)
    if (forms.size >= MAX_ALT_FORMS) break
  }
  return forms
}

/** Suffixes that are spelling noise, not real extra morphology (poshatu + n).
 * Keep nasal/visarga-like only — single vowels are too permissive (mane+i → manei). */
function isNearExactRomanSuffix(suf, fullKey) {
  if (!suf) return false
  if (!/^(n|m|ng|un|um|h)$/i.test(suf)) return false
  // Block English morphology completions (america→american, doctor→doctors)
  if (fullKey && /^(n|m)$/i.test(suf) && /(an|en|ian|ing|ers?|ors?|ly)$/i.test(fullKey)) {
    return false
  }
  return true
}

/** Soft-fill / weak lexicon weights must not outrank attested phonetics (Aksharantar=75). */
const LEXICON_STRONG_WEIGHT = 100

/**
 * True when `key` is `typed` with only ephemeral schwa 'a' inserted between consonants.
 * mne→mane is weak evidence; do not treat as TIER_EXACT.
 * a→aa lengthening (kyare→kyaare, avo→aavo) is NOT ephemeral — keep strong / exact.
 */
function isAInsertionOnly(typed, key) {
  if (!typed || !key || key === typed) return false
  if (key.length <= typed.length) return false
  let i = 0
  let j = 0
  let inserted = 0
  while (i < typed.length && j < key.length) {
    if (typed[i] === key[j]) {
      i += 1
      j += 1
      continue
    }
    if (key[j] === 'a') {
      // Extra a adjacent to an already-matched a is vowel lengthening, not schwa insert.
      if (j > 0 && key[j - 1] === 'a') return false
      j += 1
      inserted += 1
      continue
    }
    return false
  }
  if (i !== typed.length) return false
  while (j < key.length) {
    if (key[j] !== 'a') return false
    if (j > 0 && key[j - 1] === 'a') return false
    j += 1
    inserted += 1
  }
  return inserted > 0
}

/** Map lexicon hit → tier. Soft / a-insertion fuzzy never get TIER_EXACT. */
function lexiconHitTier(source, weight, typedRoman, hitRoman) {
  const w = Number(weight) || 0
  const soft = w > 0 && w < LEXICON_STRONG_WEIGHT
  if (source === 'strict' && !soft) return TIER_EXACT
  if (soft) return TIER_DICT
  if (
    source === 'fuzzy' &&
    typedRoman.startsWith('sh') &&
    hitRoman.startsWith('s') &&
    !hitRoman.startsWith('sh')
  ) {
    return TIER_DICT
  }
  if (source === 'fuzzy' && isAInsertionOnly(typedRoman, hitRoman)) return TIER_DICT
  if (source === 'near_exact' || source === 'fuzzy' || source === 'strict') return TIER_EXACT
  return TIER_DICT
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

/**
 * Learn user LM only on actual commit (called from commit_on_punct_processor).
 * Flushes immediately so personalization survives process restarts.
 * @param {Environment} env
 * @param {string} word
 */
export function learnCommittedChoice(env, word) {
  try {
    if (!word) return
    const enableUserLm = getEnvBool(env, 'translator/enable_user_lm', true)
    if (!enableUserLm) return
    loadLanguageModels(env)
    const prevWords = getContextPrevWords(env)
    // After commit, prev may already include the word; use penultimate when possible
    let prevWord = ''
    if (prevWords.length >= 2 && prevWords[prevWords.length - 1] === word) {
      prevWord = prevWords[prevWords.length - 2]
    } else if (prevWords.length >= 1 && prevWords[prevWords.length - 1] !== word) {
      prevWord = prevWords[prevWords.length - 1]
    }
    recordUserChoice(USER_LM_DEFAULT_PATH, word, prevWord, true)
    if (USER_LM_DIRTY) {
      writeUserLM(resolveUserPath(USER_LM_DEFAULT_PATH), USER_LM.wordCounts, USER_LM.bigramCounts)
      USER_LM_DIRTY = false
      USER_LM_PENDING_WRITES = 0
    }
  } catch (e) {
    console.error('$qjs$ learnCommittedChoice error:', e && e.message)
  }
}

/** Cheap roman distance for soft-gate ranking (prefer closer fuzzy hits). */
function romanCloseness(a, b) {
  if (!a || !b) return 0
  if (a === b) return 100
  const x = String(a).toLowerCase()
  const y = String(b).toLowerCase()
  if (x === y) return 100
  if (y.startsWith(x) || x.startsWith(y)) {
    return 80 - Math.min(40, Math.abs(x.length - y.length) * 8)
  }
  let shared = 0
  const n = Math.min(x.length, y.length)
  for (let i = 0; i < n; i++) {
    if (x[i] === y[i]) shared += 1
    else break
  }
  return Math.max(0, shared * 6 - Math.abs(x.length - y.length) * 4)
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
    loadEmojiKeywords(env)
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
      loadEmojiKeywords(env)

      const enableUserLm = getEnvBool(env, 'translator/enable_user_lm', true)
      const hardGate = getEnvBool(env, 'translator/lexicon_hard_gate', true)
      const fuzzyExactSoft = getEnvBool(env, 'translator/fuzzy_exact_soft', true)
      const includeLatin = getEnvBool(env, 'translator/include_latin', true)
      const emojiEnable = getEnvBool(env, 'translator/emoji_enable', true)
      const maxPrefix = Math.max(0, Math.floor(getEnvNumber(env, 'translator/max_prefix', 6)))
      const maxPhonetic = Math.max(0, Math.floor(getEnvNumber(env, 'translator/max_phonetic', 8)))
      const maxEmoji = Math.max(0, Math.floor(getEnvNumber(env, 'translator/max_emoji', 3)))
      LM_WEIGHTS.unigram = getEnvNumber(env, 'translator/lm_unigram_weight', LM_WEIGHTS.unigram)
      LM_WEIGHTS.bigram = getEnvNumber(env, 'translator/lm_bigram_weight', LM_WEIGHTS.bigram)
      LM_WEIGHTS.user = getEnvNumber(env, 'translator/lm_user_weight', LM_WEIGHTS.user)
      TRIGRAM_WEIGHT = getEnvNumber(env, 'translator/lm_trigram_weight', TRIGRAM_WEIGHT)
      const prevWords = getContextPrevWords(env)
      const prevWord = prevWords.length > 0 ? prevWords[prevWords.length - 1] : ''
      const lower = input.toLowerCase()
      const seen = new Set()
      const items = []

      function pushCand(text, comment, quality, tier, isPhonetic, romanKey, exactSource) {
        if (!text) return false
        if (seen.has(text)) {
          // Upgrade tier if a stronger source rediscovers the same native form.
          for (let i = 0; i < items.length; i++) {
            const it = items[i]
            if (it.candidate.text !== text) continue
            if (tier < it.tier) {
              it.tier = tier
              it.exactSource = exactSource || it.exactSource
              it.romanKey = romanKey || it.romanKey
              it.weight = Math.max(it.weight || 0, tier === TIER_EMOJI ? quality : lexiconWeight(romanKey || lower))
              it.closeness = Math.max(it.closeness || 0, romanCloseness(lower, romanKey || lower))
              it.candidate.comment = comment || it.candidate.comment
              return true
            }
            return false
          }
          return false
        }
        seen.add(text)
        const kind = tier === TIER_EMOJI ? 'emoji' : 'gujarati'
        const cand = new Candidate(kind, segment.start, segment.end, text, comment || '', quality)
        cand.quality = quality
        items.push({
          candidate: cand,
          tier,
          isPhonetic: !!isPhonetic,
          romanKey: romanKey || lower,
          weight: tier === TIER_EMOJI ? quality : lexiconWeight(romanKey || lower),
          exactSource: exactSource || null,
          closeness: romanCloseness(lower, romanKey || lower),
        })
        return true
      }

      // GENERAL fuzzy lexicon lookup: expand roman confusions/endings, then hit 96k Apple dict.
      // poshatu → poshatun → પોષતું; ketli → keTlii → (phonetic) કેટલી + unigram boost.
      const romanQueries = expandRomanQueries(input)
      const altForms = generateAlternateForms(lower)

      const exc = APPLE_EXCEPTIONS.get(lower) || APPLE_EXCEPTIONS.get(input)
      if (exc) {
        pushCand(exc, input, 999, TIER_EXACT, false, lower, 'strict')
      }

      const exactHits = []
      for (const q of romanQueries) {
        const word = APPLE_LEXICON.get(q) || DICT_TRIE.findExact(q)
        if (!word) continue
        const source = q === lower || q === input ? 'strict' : 'fuzzy'
        exactHits.push({
          roman: q,
          word,
          weight: Math.max(lexiconWeight(q), q === lower ? 1 : 0),
          source,
        })
      }
      exactHits.sort((a, b) => {
        // Prefer typed exact over fuzzy so a→aa soft keys cannot hide strict (kyare).
        const as = a.source === 'strict' ? 0 : 1
        const bs = b.source === 'strict' ? 0 : 1
        if (as !== bs) return as - bs
        return b.weight - a.weight || a.roman.length - b.roman.length
      })
      for (const hit of exactHits) {
        const q = hit.roman === lower ? 950 : 880
        const tier = lexiconHitTier(hit.source, hit.weight, lower, hit.roman)
        pushCand(
          hit.word,
          hit.roman === lower ? input : hit.roman,
          q + Math.min(40, Math.log1p(hit.weight) * 5),
          tier,
          false,
          hit.roman,
          hit.source
        )
      }

      // Near-exact lexicon: typed roman is a prefix of a lexicon key by only n/m/… (poshatu→poshatun)
      for (const seed of romanQueries) {
        if (seed.length < 2) continue
        for (const entry of DICT_TRIE.findPrefixEntries(seed, 12)) {
          if (!entry || !entry.value) continue
          if (!entry.key.startsWith(seed)) continue
          const suf = entry.key.slice(seed.length)
          if (!isNearExactRomanSuffix(suf, entry.key)) continue
          const w = lexiconWeight(entry.key)
          const tier = lexiconHitTier('near_exact', w, lower, entry.key)
          pushCand(entry.value, input, 900 + Math.min(50, Math.log1p(w) * 6), tier, false, entry.key, 'near_exact')
        }
      }

      const exactItems = items.filter((x) => x.tier === TIER_EXACT)
      const exactCount = exactItems.length
      const hasStrictExact = exactItems.some((x) => x.exactSource === 'strict')
      // Weak fuzzy EXACT only (rare after soft demotion): still allow attested phonetics.
      const softExactOnly =
        fuzzyExactSoft &&
        exactCount > 0 &&
        !hasStrictExact &&
        exactItems.every((x) => (x.weight || 0) < LEXICON_STRONG_WEIGHT)

      // Latin only after we know exact/dict tiers will sort above it
      if (includeLatin) {
        pushCand(input, '', 400, TIER_LATIN, false, lower, null)
      }

      // Generate phonetics, then RESCORE with native wordlist/stems/spell-dicts.
      // Indic IME grammar: schwa-default + productive conjuncts + nasal final -u.
      const phoneticForms = []
      const seenPhon = new Set()
      function addPhon(g) {
        if (!g || g === input || g === lower || seenPhon.has(g) || seen.has(g)) return
        seenPhon.add(g)
        phoneticForms.push(g)
      }
      for (const g of phoneticFormsForRoman(input)) addPhon(g)
      for (const form of altForms) {
        if (form.toLowerCase() === lower) continue
        for (const g of phoneticFormsForRoman(form)) addPhon(g)
      }

      const phonScored = []
      for (const text of phoneticForms) {
        if (seen.has(text)) continue
        const known = KNOWN_WORDS.has(text)
        const validity = dictionaryValidity(text)
        // Hard-gate: with a strict lexicon exact, drop invented phonetics (classic).
        // Soft: fuzzy/near-exact-only (low weight) still allows attested / spell-dict forms.
        // Soft-fill / a-insertion hits are TIER_DICT (not EXACT), so exactCount stays 0 and
        // high-frequency phonetics can outrank them (mne → મને over soft mane→માને).
        if (hardGate && exactCount > 0 && !known) {
          if (hasStrictExact) {
            continue
          }
          if (softExactOnly) {
            if (!validity.attested && !validity.spellOk) continue
          } else {
            continue
          }
        }
        phonScored.push({ text, known, validity })
      }
      phonScored.sort((a, b) => {
        if (a.validity.spellOk !== b.validity.spellOk) return a.validity.spellOk ? -1 : 1
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
        if (pushCand(item.text, input, q, tier, true, lower, null)) phoneticAdded += 1
      }

      if (exactCount === 0 && phoneticAdded === 0) {
        const fallback = phoneticFormsForRoman(input)[0]
        if (fallback && fallback !== input) {
          const v = dictionaryValidity(fallback)
          pushCand(fallback, input, v.attested ? 720 : 250, v.attested ? TIER_DICT : TIER_PHONETIC, true, lower, null)
        }
      }

      if (input.length >= 2 && maxPrefix > 0) {
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
          let suffix = ''
          if (entry.key.startsWith(lower)) suffix = entry.key.slice(lower.length)
          else {
            suffix = entry.key.length > lower.length ? entry.key.slice(lower.length) : ''
          }
          const w = lexiconWeight(entry.key)
          if (entry.key.startsWith(lower) && isNearExactRomanSuffix(suffix, entry.key)) {
            const tier = lexiconHitTier('near_exact', w, lower, entry.key)
            if (pushCand(entry.value, input, 860 + Math.min(40, Math.log1p(w) * 5), tier, false, entry.key, 'near_exact')) {
              prefixAdded += 1
            }
            continue
          }
          if (entry.key === lower) continue
          const comment = suffix ? ('~' + suffix) : input
          if (pushCand(entry.value, comment, 80 + Math.min(40, Math.log1p(w) * 5), TIER_PREFIX, false, entry.key, null)) {
            prefixAdded += 1
          }
        }
      }

      // Emoji suggestions from English / Gujarati-roman keywords (never beat script tiers).
      if (emojiEnable && maxEmoji > 0 && EMOJI_BY_ROMAN.size > 0) {
        const emojiHits = []
        const seenEmoji = new Set()
        function queueEmoji(list, via) {
          if (!list) return
          for (const it of list) {
            if (!it || !it.e || seenEmoji.has(it.e) || seen.has(it.e)) continue
            seenEmoji.add(it.e)
            emojiHits.push({ emoji: it.e, weight: it.w || 100, via })
          }
        }
        queueEmoji(EMOJI_BY_ROMAN.get(lower), lower)
        for (const q of romanQueries) {
          if (q !== lower) queueEmoji(EMOJI_BY_ROMAN.get(q), q)
        }
        // Native forms already in the menu (e.g. પ્રેમ from prem)
        for (const item of items) {
          if (item.tier === TIER_EMOJI) continue
          queueEmoji(EMOJI_BY_NATIVE.get(item.candidate.text), item.candidate.text)
          if (item.romanKey) queueEmoji(EMOJI_BY_ROMAN.get(item.romanKey), item.romanKey)
        }
        emojiHits.sort((a, b) => b.weight - a.weight)
        let emojiAdded = 0
        for (const hit of emojiHits) {
          if (emojiAdded >= maxEmoji) break
          if (pushCand(hit.emoji, 'emoji', 50 + Math.min(40, Math.log1p(hit.weight) * 4), TIER_EMOJI, false, lower, null)) {
            emojiAdded += 1
          }
        }
      }

      if (items.length === 0) return []

      const scored = items.map((item, index) => {
        const text = item.candidate.text || ''
        const lm = item.tier === TIER_EMOJI
          ? Math.log1p(item.weight || 0) * 0.2
          : scoreCandidateWithContext(text, prevWords, item.isPhonetic)
        const freq = Math.log1p(item.weight || 0) * 0.35
        const validity = item.tier === TIER_EMOJI
          ? { score: 0, attested: false, evidence: 0, spellOk: false }
          : dictionaryValidity(text)
        const dictBoost = validity.attested ? validity.score * 1.4 : 0
        const spellBoost = validity.spellOk ? 0.35 : 0
        const closeBoost = (item.closeness || 0) * 0.01
        const unigramCount = UNIGRAM_LM.map.get(text) || 0
        const uniBoost = Math.log1p(unigramCount) * 0.55
        let score = lm + freq + dictBoost + spellBoost + closeBoost + uniBoost
        let tier = item.tier
        const isLex = item.exactSource === 'strict' || item.exactSource === 'fuzzy' || item.exactSource === 'near_exact'
        if (isLex && (item.weight || 0) > 0 && (item.weight || 0) < LEXICON_STRONG_WEIGHT && unigramCount < 150) {
          score -= freq * 0.85 + 2.8
        }
        if (text.includes('ય') && !lower.includes('y')) score -= 4.0
        if (lower.includes('d') && !/(^|[^a-z])D/.test(lower)) {
          if (text.includes('ડ') && !text.includes('દ')) score -= 1.2
          if (text.includes('દ')) score += 0.5
        }
        if (lower.startsWith('sh')) {
          if (text.startsWith('શ')) score += 3.0
          else if (text.startsWith('સ')) score -= 3.0 + uniBoost * 0.5
        } else if (!lower.includes('sh') && lower.includes('s')) {
          if (text.includes('શ') && !text.includes('ષ')) score -= 0.55
          if (text.includes('સ') && !text.includes('શ')) score += 0.15
        }
        if (lower.includes('z') && !lower.includes('j')) {
          if (text.startsWith('ઝ')) score += 0.5
          else if (text.startsWith('જ')) score -= 0.35
        }
        if (/(mm|nn|tt|kk|ll)/.test(lower)) {
          if (text.includes('\u0ACD')) score += 3.0
          if (text.includes(ANUSVARA) && !text.includes('\u0ACD')) {
            score -= 3.5 + uniBoost * 0.65
            if (tier === TIER_EXACT) tier = TIER_DICT
          }
        } else if (text.includes(ANUSVARA) && /n[kgcjtdTDpb]/.test(lower)) {
          score += 0.35
        }
        const aVowels = (lower.match(/a+/g) || []).length
        let aa = 0
        for (const ch of text) if (ch === 'ા') aa += 1
        let effectiveAa = aa
        if (text.endsWith('ા') && !lower.endsWith('a') && !lower.endsWith('aa')) {
          effectiveAa = Math.max(0, effectiveAa - 1)
          score -= 1.6
        }
        if (aVowels >= 1 && lower.slice(1).includes('a')) {
          score += 0.2 * effectiveAa
          if (aVowels >= 2 && effectiveAa >= 2) score += 2.5
          else if (aVowels >= 2 && effectiveAa < 2) score -= 1.2
        }
        if (text.length < lower.length * 0.7) score -= 2.0
        return { ...item, score, validity, index, tier }
      })

      scored.sort((a, b) => {
        if (a.tier !== b.tier) return a.tier - b.tier
        if (b.score !== a.score) return b.score - a.score
        if ((b.closeness || 0) !== (a.closeness || 0)) return (b.closeness || 0) - (a.closeness || 0)
        if ((b.weight || 0) !== (a.weight || 0)) return (b.weight || 0) - (a.weight || 0)
        return a.index - b.index
      })

      // User LM is learned on commit only (see learnCommittedChoice / commit_on_punct).
      void enableUserLm

      const sortedCandidates = scored.map((item, rank) => {
        const c = item.candidate
        // TIER_EMOJI=TIER_MAX → base 0 so script candidates always outrank emoji.
        c.quality = (TIER_MAX - item.tier) * 200 + Math.max(0, 180 - rank)
        return c
      })

      return sortedCandidates
    } catch (e) {
      console.error('$qjs$ translate error:', e.message)
      return []
    }
  }
}
