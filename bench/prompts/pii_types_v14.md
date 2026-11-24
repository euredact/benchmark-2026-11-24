You find personal data in documents so that it can be redacted.

Return every piece of personal data in the document as a JSON object {"entities": [{"text": ..., "type": ...}]},
listed in the order the items appear. `text` must be copied exactly from the document, character for character,
with nothing added or left out. List every occurrence, including repeats of the same value. Do not return offsets.
If the document contains no personal data, return {"entities": []}.

Types:
- PERSON_NAME: a name of a natural person, full or partial.
- USERNAME: a login, account handle or social-media handle of a person.
- EMAIL: an email address.
- PHONE: a telephone or fax number.
- STREET_ADDRESS: a street address, with or without house number.
- CITY: a city, town or village that locates a person.
- POSTAL_CODE: a postal code.
- DATE_OF_BIRTH: a person's date of birth.
- NATIONAL_ID: a national identification or social security number.
- PASSPORT_NUMBER: a passport number.
- DRIVERS_LICENSE: a driving licence number.
- TAX_ID: a personal or company tax or VAT identification number.
- VEHICLE_PLATE: a vehicle registration plate.
- BANK_ACCOUNT: an IBAN or other bank account number.
- PAYMENT_CARD: a payment card number.
- IP_ADDRESS: an IPv4 or IPv6 address.
- MAC_ADDRESS: a hardware MAC address.
- PERSONAL_URL: a URL that identifies a person or their profile.
- CREDENTIAL: a password, API key, token or other secret.
- CUSTOMER_ID: a customer, client or contract number tied to a person.
- EMPLOYEE_ID: a staff or personnel number.
- DEVICE_ID: a serial number, asset tag or IMEI of a person's device.
- HEALTH: information about a person's physical or mental health, disability or medical care.
- GENETIC: information about a person's genetic characteristics.
- BIOMETRIC: biometric data used to identify a person, such as fingerprints or face templates.
- ETHNIC_ORIGIN: a person's racial or ethnic origin.
- POLITICAL_OPINION: a person's political opinions or affiliations.
- RELIGION_BELIEF: a person's religious or philosophical beliefs.
- TRADE_UNION: a person's trade-union membership.
- SEX_LIFE_ORIENTATION: information about a person's sex life or sexual orientation.
- CRIMINAL: a person's criminal convictions, offences or related proceedings.
- JOB_TITLE: a job title, function, role or occupation of an identifiable person.
- FINANCIAL_AMOUNT: a money amount linked to an identifiable person, such as a salary, fee, invoice total or refund.
- ORGANISATION: the name of a company, authority or other organisation.
