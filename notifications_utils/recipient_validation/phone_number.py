import re
from collections import namedtuple
from contextlib import suppress

import phonenumbers
from flask import current_app

from notifications_utils.formatters import (
    ALL_WHITESPACE,
)
from notifications_utils.international_billing_rates import (
    COUNTRY_PREFIXES,
    INTERNATIONAL_BILLING_RATES,
)
from notifications_utils.recipient_validation.errors import InvalidPhoneError

UK_PREFIX = "44"


international_phone_info = namedtuple(
    "PhoneNumber",
    [
        "international",
        "crown_dependency",
        "country_prefix",
        "billable_units",
    ],
)


def normalise_phone_number(number):
    for character in ALL_WHITESPACE + "()-+":
        number = number.replace(character, "")

    try:
        list(map(int, number))
    except ValueError as e:
        raise InvalidPhoneError(code=InvalidPhoneError.Codes.UNKNOWN_CHARACTER) from e

    return number.lstrip("0")


def is_uk_phone_number(number):
    if number.startswith("0") and not number.startswith("00"):
        return True

    number = normalise_phone_number(number)

    if number.startswith(UK_PREFIX) or (number.startswith("7") and len(number) < 11):
        return True

    return False


def get_international_phone_info(number):
    number = validate_phone_number(number, international=True)
    prefix = get_international_prefix(number)
    crown_dependency = _is_a_crown_dependency_number(number)

    return international_phone_info(
        international=(prefix != UK_PREFIX or crown_dependency),
        crown_dependency=crown_dependency,
        country_prefix=prefix,
        billable_units=get_billable_units_for_prefix(prefix),
    )


CROWN_DEPENDENCY_RANGES = ["7781", "7839", "7911", "7509", "7797", "7937", "7700", "7829", "7624", "7524", "7924"]


def _is_a_crown_dependency_number(number):
    num_in_crown_dependency_range = number[2:6] in CROWN_DEPENDENCY_RANGES
    num_in_tv_range = number[2:9] == "7700900"

    return num_in_crown_dependency_range and not num_in_tv_range


def get_international_prefix(number):
    return next((prefix for prefix in COUNTRY_PREFIXES if number.startswith(prefix)), None)


def get_billable_units_for_prefix(prefix):
    return INTERNATIONAL_BILLING_RATES[prefix]["billable_units"]


def use_numeric_sender(number):
    prefix = get_international_prefix(normalise_phone_number(number))
    return INTERNATIONAL_BILLING_RATES[prefix]["attributes"]["alpha"] == "NO"


def validate_uk_phone_number(number):
    number = normalise_phone_number(number).lstrip(UK_PREFIX).lstrip("0")

    if not number.startswith("7"):
        raise InvalidPhoneError(code=InvalidPhoneError.Codes.NOT_A_UK_MOBILE)

    if len(number) > 10:
        raise InvalidPhoneError(code=InvalidPhoneError.Codes.TOO_LONG)

    if len(number) < 10:
        raise InvalidPhoneError(code=InvalidPhoneError.Codes.TOO_SHORT)

    return f"{UK_PREFIX}{number}"


def validate_phone_number(number, international=False):
    if (not international) or is_uk_phone_number(number):
        return validate_uk_phone_number(number)

    number = normalise_phone_number(number)

    if len(number) < 8:
        raise InvalidPhoneError(code=InvalidPhoneError.Codes.TOO_SHORT)

    if len(number) > 15:
        raise InvalidPhoneError(code=InvalidPhoneError.Codes.TOO_LONG)

    if get_international_prefix(number) is None:
        raise InvalidPhoneError(code=InvalidPhoneError.Codes.UNSUPPORTED_COUNTRY_CODE)

    return number


validate_and_format_phone_number = validate_phone_number


def try_validate_and_format_phone_number(number, international=None, log_msg=None):
    """
    For use in places where you shouldn't error if the phone number is invalid - for example if firetext pass us
    something in
    """
    try:
        return validate_and_format_phone_number(number, international)
    except InvalidPhoneError as exc:
        if log_msg:
            current_app.logger.warning("%s: %s", log_msg, exc)
        return number


def format_phone_number_human_readable(phone_number):
    try:
        phone_number = validate_phone_number(phone_number, international=True)
    except InvalidPhoneError:
        # if there was a validation error, we want to shortcut out here, but still display the number on the front end
        return phone_number
    international_phone_info = get_international_phone_info(phone_number)

    return phonenumbers.format_number(
        phonenumbers.parse("+" + phone_number, None),
        (
            phonenumbers.PhoneNumberFormat.INTERNATIONAL
            if international_phone_info.international
            else phonenumbers.PhoneNumberFormat.NATIONAL
        ),
    )


class PhoneNumber:
    """
    A class that contains phone number validation.

    Supports mobile and landline numbers. When creating an object you must specify whether you are expecting
    international phone numbers to be allowed or not.
    """

    def __init__(self, phone_number: str, *, allow_international: bool) -> None:
        self.raw_input = phone_number
        self.allow_international = allow_international
        try:
            self.number = self.validate_phone_number(phone_number)
        except InvalidPhoneError:
            phone_number = self._thoroughly_normalise_number(phone_number)
            self.number = self.validate_phone_number(phone_number)
        self._raise_if_service_cannot_send_to_international_but_tries_to(phone_number)

    def _raise_if_service_cannot_send_to_international_but_tries_to(self, phone_number):
        number = self._try_parse_number(phone_number)
        if not self.allow_international and str(number.country_code) != UK_PREFIX:
            raise InvalidPhoneError(code=InvalidPhoneError.Codes.NOT_A_UK_MOBILE)

    @staticmethod
    def _try_parse_number(phone_number):
        try:
            # parse number as GB - if there's no country code, try and parse it as a UK number
            return phonenumbers.parse(phone_number, "GB")
        except phonenumbers.NumberParseException as e:
            raise InvalidPhoneError(code=InvalidPhoneError.Codes.INVALID_NUMBER) from e

    @staticmethod
    def _raise_if_phone_number_contains_invalid_characters(number: str) -> None:
        chars = set(number)
        if chars - {*ALL_WHITESPACE + "()-+" + "0123456789"}:
            raise InvalidPhoneError(code=InvalidPhoneError.Codes.UNKNOWN_CHARACTER)

    def validate_phone_number(self, phone_number: str) -> phonenumbers.PhoneNumber:
        """
        Validate a phone number and return the PhoneNumber object

        Tries best effort validation, and has some extra logic to make the validation closer to our existing validation
        including:

        * Being stricter with rogue alphanumeric characters. (eg don't allow https://en.wikipedia.org/wiki/Phoneword)
        * Additional parsing steps to check if there was a + or leading 0 stripped off the beginning of the number that
          changes whether it is parsed as international or not.
        * Convert error codes to match existing Notify error codes
        """
        # notify's old validation code is stricter than phonenumbers in not allowing letters etc, so need to catch some
        # of those cases separately before we parse with the phonenumbers library
        self._raise_if_phone_number_contains_invalid_characters(phone_number)

        number = self._try_parse_number(phone_number)

        if str(number.country_code) not in COUNTRY_PREFIXES + ["+44"]:
            raise InvalidPhoneError(code=InvalidPhoneError.Codes.UNSUPPORTED_COUNTRY_CODE)

        if (reason := phonenumbers.is_possible_number_with_reason(number)) != phonenumbers.ValidationResult.IS_POSSIBLE:
            if self.allow_international and (
                forced_international_number := self._validate_forced_international_number(phone_number)
            ):
                number = forced_international_number
            else:
                raise InvalidPhoneError.from_phonenumbers_validation_result(reason)

        if not phonenumbers.is_valid_number(number):
            # is_possible just checks the length of a number for that country/region. is_valid checks if it's
            # a valid sequence of numbers. This doesn't cover "is this number registered to an MNO".
            # For example UK numbers cannot start "06" as that hasn't been assigned to a purpose by ofcom
            if self._is_tv_number(number):
                return number
            else:
                raise InvalidPhoneError(code=InvalidPhoneError.Codes.INVALID_NUMBER)

        return number

    @staticmethod
    def _is_tv_number(phone_number) -> bool:
        """
        The phonenumbers library does not consider TV numbers (fake numbers OFCOM reserves use in TV, film etc)
        valid. This method checks whether a normalised phone number that has failed the library's validation is
        in fact a valid TV number
        """
        phone_number_as_string = str(phone_number.national_number)
        if re.match("7700[900000-900999]", phone_number_as_string):
            return True

    @staticmethod
    def _thoroughly_normalise_number(phone_number: str) -> str:
        """
        We often (up to ~3% of the time) see numbers which are not technically valid, but are close-enough-to-valid
        that we want to give our users benefit of the doubt.

        We don't want to do this for every number, because if someone passes in a valid international number that
        like "+1 (500) 555-1234" then we don't want to remove the + sign as we may then confuse it with a UK landline

        This includes numbers like:

        "0+447700900100" (a stray leading 0)
        "000007700900100" (five leading zeros)
        "+07700900100" (a leading plus but no country code)
        "0+44(0)7700900100" (a mix of all of the above)
        """
        return phone_number.replace("+", "").lstrip("0")

    @staticmethod
    def _validate_forced_international_number(phone_number: str) -> phonenumbers.PhoneNumber | None:
        """
        phonenumbers assumes a number without a + or 00 at beginning is always a local number. Given that we know excel
        sometimes strips these, if it doesn't parse as a UK number, lets try forcing it to be recognised as an
        international number
        """
        with suppress(phonenumbers.NumberParseException):
            forced_international_number = phonenumbers.parse(f"+{phone_number}")

            if phonenumbers.is_possible_number(forced_international_number):
                return forced_international_number

        return None

    @property
    def prefix(self):
        """
        Returns the international dialing code for looking up data in our international_billing_rates.yml file

        in our billing rates yml file, countries in the North American Numbering Plan (+1) may fall under
        US/Canada/Dominican Republic (just +1) or they may have their own specific area code within the plan, eg
        Montserrat with numbers like "+1 664 xxx xxxx". This means we need to check the area code first to see if
        it's a regular area code or a full country code.
        """
        if self.number.country_code == 1:
            country_and_area_code = phonenumbers.format_number(self.number, phonenumbers.PhoneNumberFormat.E164)[1:5]
            if country_and_area_code in INTERNATIONAL_BILLING_RATES:
                return country_and_area_code
        return str(self.number.country_code)

    def is_uk_phone_number(self):
        """
        Returns if the number starts with +44. Note, this includes international numbers for crown dependencies such as
        jersey/guernsey.

        # TODO: check if we still need this - looking at api, this might be able to be removed entirely since it's
        # always used in conjunction with should_use_numeric_sender
        """
        return self.number.country_code == 44

    def get_international_phone_info(self):
        return international_phone_info(
            international=phonenumbers.region_code_for_number(self.number) != "GB",
            crown_dependency=self._is_a_crown_dependency_number(),
            country_prefix=self.prefix,
            billable_units=INTERNATIONAL_BILLING_RATES[self.prefix]["billable_units"],
        )

    def _is_a_crown_dependency_number(self):
        """
        Returns True for phone numbers from Jersey, Guernsey, Isle of Man, etc
        """
        return self.is_uk_phone_number() and phonenumbers.region_code_for_number(self.number) != "GB"

    def should_use_numeric_sender(self):
        """
        Some countries need a specific sender to be used rather than whatever the service has specified
        """
        return INTERNATIONAL_BILLING_RATES[self.prefix]["attributes"]["alpha"] == "NO"

    def get_normalised_format(self):
        return str(self)

    def __str__(self):
        """
        Returns a normalised phone number including international country code suitable to send to providers
        """
        formatted = phonenumbers.format_number(self.number, phonenumbers.PhoneNumberFormat.E164)
        # strip the plus and just pass numbers to our suppliers.
        # TODO: If our suppliers let us send the plus, then we should do so, for consistency/accuracy.
        return formatted[1:]

    def get_human_readable_format(self):
        # comparable to `format_phone_number_human_readable`
        return phonenumbers.format_number(
            self.number,
            (
                phonenumbers.PhoneNumberFormat.INTERNATIONAL
                if self.number.country_code != 44
                else phonenumbers.PhoneNumberFormat.NATIONAL
            ),
        )
