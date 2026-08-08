'use strict';

// The profile schema, and everything needed to recognise each item in a form.
//
// Application portals are in English, German or Dutch, so keywords are listed
// per language. `autocomplete` tokens are listed first because they are the
// only signal a form gives deliberately — when present they are close to
// authoritative, and the matcher weights them accordingly.
//
// `sensitive: true` marks items that identify the holder rather than describe
// them. Those are never filled unless the user turns them on for that fill.

const FIELD_DEFS = [
  // -- who you are ------------------------------------------------------
  {
    key: 'firstName', group: 'personal', label: 'Ad',
    autocomplete: ['given-name'],
    keywords: ['first name', 'given name', 'forename', 'firstname',
      'vorname', 'voornaam', 'ad', 'isim'],
  },
  {
    key: 'middleName', group: 'personal', label: 'İkinci ad',
    autocomplete: ['additional-name'],
    keywords: ['middle name', 'middlename', 'zweiter vorname', 'tussenvoegsel'],
  },
  {
    key: 'lastName', group: 'personal', label: 'Soyad',
    autocomplete: ['family-name'],
    keywords: ['last name', 'surname', 'family name', 'lastname',
      'nachname', 'familienname', 'achternaam', 'familienaam', 'soyad', 'soyisim'],
  },
  {
    key: 'dateOfBirth', group: 'personal', label: 'Doğum tarihi',
    autocomplete: ['bday'], inputType: 'date',
    keywords: ['date of birth', 'birth date', 'birthdate', 'dob', 'birthday',
      'geburtsdatum', 'geboortedatum', 'doğum tarihi'],
  },
  {
    key: 'placeOfBirth', group: 'personal', label: 'Doğum yeri',
    keywords: ['place of birth', 'birth place', 'birthplace',
      'geburtsort', 'geboorteplaats', 'doğum yeri'],
  },
  {
    key: 'countryOfBirth', group: 'personal', label: 'Doğum ülkesi',
    keywords: ['country of birth', 'geburtsland', 'geboorteland'],
  },
  {
    key: 'nationality', group: 'personal', label: 'Uyruk',
    keywords: ['nationality', 'citizenship',
      'staatsangehörigkeit', 'staatsangehoerigkeit', 'nationalität',
      'nationaliteit', 'uyruk', 'vatandaşlık'],
  },
  {
    key: 'gender', group: 'personal', label: 'Cinsiyet',
    autocomplete: ['sex'],
    keywords: ['gender', 'sex', 'geschlecht', 'geslacht', 'cinsiyet'],
  },

  // -- how to reach you -------------------------------------------------
  {
    key: 'email', group: 'contact', label: 'E-posta',
    autocomplete: ['email'], inputType: 'email',
    keywords: ['email', 'e-mail', 'mail address', 'e-mailadres', 'e-posta'],
  },
  {
    key: 'phone', group: 'contact', label: 'Telefon',
    autocomplete: ['tel'], inputType: 'tel',
    keywords: ['phone', 'telephone', 'mobile', 'telefon', 'handy', 'mobiel',
      'telefoonnummer', 'cep'],
  },
  {
    key: 'street', group: 'contact', label: 'Sokak / adres',
    autocomplete: ['street-address', 'address-line1'],
    keywords: ['street', 'address line', 'address', 'straße', 'strasse',
      'anschrift', 'adresse', 'straat', 'adres', 'sokak'],
  },
  {
    key: 'houseNumber', group: 'contact', label: 'Bina / kapı no',
    keywords: ['house number', 'street number', 'hausnummer', 'huisnummer',
      'bina no', 'kapı no'],
  },
  {
    key: 'postalCode', group: 'contact', label: 'Posta kodu',
    autocomplete: ['postal-code'],
    keywords: ['postal code', 'postcode', 'zip', 'plz', 'postleitzahl',
      'posta kodu'],
  },
  {
    key: 'city', group: 'contact', label: 'Şehir',
    autocomplete: ['address-level2'],
    keywords: ['city', 'town', 'stadt', 'wohnort', 'ort', 'woonplaats',
      'plaats', 'şehir'],
  },
  {
    key: 'country', group: 'contact', label: 'Ülke',
    autocomplete: ['country', 'country-name'],
    keywords: ['country', 'land', 'ülke'],
  },

  // -- identity documents (sensitive) -----------------------------------
  {
    key: 'passportNumber', group: 'identity', label: 'Pasaport numarası',
    sensitive: true,
    keywords: ['passport number', 'passport no', 'passport',
      'reisepass', 'passnummer', 'paspoortnummer', 'paspoort', 'pasaport'],
  },
  {
    key: 'passportExpiry', group: 'identity', label: 'Pasaport geçerlilik tarihi',
    sensitive: true, inputType: 'date',
    keywords: ['passport expiry', 'passport valid until', 'gültig bis',
      'geldig tot'],
  },
  {
    key: 'nationalId', group: 'identity', label: 'T.C. kimlik numarası',
    sensitive: true,
    keywords: ['national id', 'identity number', 'id number', 'personal number',
      'ausweisnummer', 'bsn', 'kimlik numarası', 'tc kimlik'],
  },

  // -- previous degree --------------------------------------------------
  {
    key: 'institution', group: 'education', label: 'Mezun olduğun üniversite',
    keywords: ['university', 'institution', 'higher education institution',
      'previous institution', 'hochschule', 'universität', 'universiteit',
      'instelling', 'üniversite'],
  },
  {
    key: 'degree', group: 'education', label: 'Derece',
    keywords: ['degree', 'qualification', 'abschluss', 'studienabschluss',
      'diploma', 'graad', 'derece'],
  },
  {
    key: 'fieldOfStudy', group: 'education', label: 'Bölüm / alan',
    keywords: ['field of study', 'major', 'subject', 'programme of study',
      'studienfach', 'fachrichtung', 'studierichting', 'vakgebied', 'bölüm'],
  },
  {
    key: 'gpa', group: 'education', label: 'Not ortalaması',
    keywords: ['gpa', 'grade point average', 'final grade', 'average grade',
      'durchschnittsnote', 'abschlussnote', 'note', 'gemiddeld cijfer',
      'not ortalaması'],
  },
  {
    key: 'gpaScale', group: 'education', label: 'Not sistemi (ör. 4.00)',
    keywords: ['grading scale', 'grade scale', 'maximum grade', 'notenskala',
      'cijferschaal'],
  },
  {
    key: 'ects', group: 'education', label: 'Toplam ECTS',
    keywords: ['ects', 'credits', 'credit points', 'leistungspunkte',
      'studiepunten'],
  },
  {
    key: 'graduationDate', group: 'education', label: 'Mezuniyet tarihi',
    inputType: 'date',
    keywords: ['graduation date', 'date of graduation', 'date of award',
      'abschlussdatum', 'afstudeerdatum', 'mezuniyet tarihi'],
  },

  // -- language tests ---------------------------------------------------
  {
    key: 'ieltsOverall', group: 'language', label: 'IELTS genel puan',
    keywords: ['ielts overall', 'ielts band', 'ielts score', 'ielts'],
  },
  {
    key: 'ieltsDate', group: 'language', label: 'IELTS sınav tarihi',
    inputType: 'date',
    keywords: ['ielts date', 'ielts test date'],
  },
  {
    key: 'toeflTotal', group: 'language', label: 'TOEFL toplam puan',
    keywords: ['toefl total', 'toefl score', 'toefl ibt', 'toefl'],
  },
  {
    key: 'toeflDate', group: 'language', label: 'TOEFL sınav tarihi',
    inputType: 'date',
    keywords: ['toefl date', 'toefl test date'],
  },
];

const GROUP_LABELS = {
  personal: 'Kişisel',
  contact: 'İletişim',
  identity: 'Kimlik belgeleri (hassas)',
  education: 'Önceki eğitim',
  language: 'Dil sınavları',
};

// Inputs whose signature matches any of these are never filled, whatever the
// score and whatever the user has enabled. Credentials and payment details are
// not this tool's business, and a form asking for them next to an application
// form is a reason to stop, not to autofill.
const NEVER_FILL = new RegExp([
  'pass(word|wort|woord)', 'wachtwoord', 'şifre', 'parola',
  'credit.?card', 'card.?number', 'kreditkart', 'creditcard',
  'cvv', 'cvc', 'security.?code', 'card.?verification',
  'iban', '\\bbic\\b', 'swift', 'sort.?code', 'routing',
  'account.?number', 'kontonummer', 'rekeningnummer',
  '\\bpin\\b', 'otp', 'one.?time', 'verification.?code', '2fa',
].join('|'), 'i');

const NEVER_FILL_TYPES = new Set(['password', 'hidden', 'file', 'submit',
  'button', 'image', 'reset']);

if (typeof module !== 'undefined') {
  module.exports = { FIELD_DEFS, GROUP_LABELS, NEVER_FILL, NEVER_FILL_TYPES };
}
