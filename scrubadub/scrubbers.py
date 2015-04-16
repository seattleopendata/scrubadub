import re

import textblob
import phonenumbers
import nltk

from . import exceptions
from . import regexps


class Scrubber(object):
    """The Scrubber class is used to clean personal information out of
    dirty dirty text.
    """

    def __init__(self, **kwargs):
        super(Scrubber, self).__init__()
        self.configure(**kwargs)

    def configure(self, **kwargs):
        """The configure method sets up all of the scrubber options.

        TKTK SHOULD PROBABLY ADD A USEFUL DESCRIPTION IN THE DOCUMENTATION
        SOMEWHERE ABOUT THE DIFFERENT CONFIGURATION OPTIONS. THESE
        DOCUMENTATION CHANGES SHOULD PROPAGATE TO ALL METHODS, TOO
        """

        # get all of the replacement names
        self.proper_noun_replacement = \
            kwargs.get('proper_noun_replacement', "{{NAME}}")
        self.email_replacement = \
            kwargs.get('email_replacement', "{{EMAIL}}")
        self.url_replacement = \
            kwargs.get('url_replacement', "{{URL}}")
        self.phone_replacement = \
            kwargs.get('phone_replacement', "{{PHONE}}")
        self.username_replacement = \
            kwargs.get('username_replacement', "{{USERNAME}}")
        self.password_replacement = \
            kwargs.get('password_replacement', "{{PASSWORD}}")
        self.skype_replacement = \
            kwargs.get('skype_replacement', "{{SKYPE}}")

        # other options for different scrubber methods
        self.url_keep_domain = kwargs.get('url_keep_domain', False)
        self.phone_region = kwargs.get('phone_region', "US")
        self.skype_word_radius = kwargs.get('skype_word_radius', 10)

    def clean_with_placeholders(self, text):
        """This is the master method that cleans all of the filth out of the
        dirty dirty ``text`` using the default options for all of the other
        ``clean_*`` methods below.
        """
        if not isinstance(text, unicode):
            raise exceptions.UnicodeRequired

        # * phone numbers needs to come before email addresses (#8)
        # * credentials need to come before email addresses (#9)
        # * skype needs to come before email addresses
        text = self.clean_proper_nouns(text)
        text = self.clean_urls(text)
        text = self.clean_phone_numbers(text)
        text = self.clean_credentials(text)
        text = self.clean_skype(text)
        text = self.clean_email_addresses(text)
        return text

    def clean_proper_nouns(self, text):
        """Use part of speech tagging to clean proper nouns out of the dirty
        dirty ``text``.
        """

        # find the set of proper nouns using textblob. disallowed_nouns is a
        # workaround to make sure that downstream processing works correctly
        disallowed_nouns = set(["skype"])
        proper_nouns = set()
        blob = textblob.TextBlob(text)
        for word, part_of_speech in blob.tags:
            is_proper_noun = part_of_speech in ("NNP", "NNPS")
            if is_proper_noun and word.lower() not in disallowed_nouns:
                proper_nouns.add(word)

        # use a regex to replace the proper nouns by first escaping any
        # lingering punctuation in the regex
        # http://stackoverflow.com/a/4202559/564709
        for proper_noun in proper_nouns:
            proper_noun_re = r'\b' + re.escape(proper_noun) + r'\b'
            text = re.sub(proper_noun_re, self.proper_noun_replacement, text)
        return text

    def clean_email_addresses(self, text):
        """Use regular expression magic to remove email addresses from dirty
        dirty ``text``. This method also catches email addresses like ``john at
        gmail.com``.
        """
        return regexps.EMAIL.sub(self.email_replacement, text)

    def clean_urls(self, text):
        """Use regular expressions to remove URLs that begin with ``http://``,
        ``https://`` or ``www.`` from dirty dirty ``text``.

        With ``keep_domain=True``, this method only obfuscates the path on a
        URL, not its domain. For example,
        ``http://twitter.com/someone/status/234978haoin`` becomes
        ``http://twitter.com/{{replacement}}``.
        """
        for match in regexps.URL.finditer(text):
            beg = match.start()
            end = match.end()
            if self.url_keep_domain:
                replacement = match.group('domain') + self.url_replacement
            else:
                replacement = self.url_replacement
            text = text.replace(match.string[beg:end], replacement)
        return text

    def clean_phone_numbers(self, text):
        """Remove phone numbers from dirty dirty ``text`` using
        `python-phonenumbers
        <https://github.com/daviddrysdale/python-phonenumbers>`_, a port of a
        Google project to correctly format phone numbers in text.

        ``region`` specifies the best guess region to start with (default:
        ``"US"``). Specify ``None`` to only consider numbers with a leading
        ``+`` to be considered.
        """
        # create a copy of text to handle multiple phone numbers correctly
        result = text
        for match in phonenumbers.PhoneNumberMatcher(text, self.phone_region):
            result = result.replace(
                text[match.start:match.end],
                self.phone_replacement,
            )
        return result

    def clean_credentials(self, text):
        """Remove username/password combinations from dirty drity ``text``.
        """
        position = 0
        while True:
            match = regexps.CREDENTIALS.search(text, position)
            if match:
                ubeg, uend = match.span('username')
                pbeg, pend = match.span('password')
                text = (
                    text[:ubeg] + self.username_replacement + text[uend:pbeg] +
                    self.password_replacement + text[pend:]
                )
                position = match.end()
            else:
                break
        return text

    def clean_skype(self, text):
        """Skype usernames tend to be used inline in dirty dirty text quite
        often but also appear as ``skype: {{SKYPE}}`` quite a bit. This method
        looks at words within ``word_radius`` words of "skype" for things that
        appear to be misspelled or have punctuation in them as a means to
        identify skype usernames.

        Default ``word_radius`` is 10, corresponding with the rough scale of
        half of a sentence before or after the word "skype" is used. Increasing
        the ``word_radius`` will increase the false positive rate and
        decreasing the ``word_radius`` will increase the false negative rate.
        """

        # find 'skype' in the text using a customized tokenizer. this makes
        # sure that all valid skype usernames are kept as tokens and not split
        # into different words
        tokenizer = nltk.tokenize.regexp.RegexpTokenizer(regexps.SKYPE_TOKEN)
        blob = textblob.TextBlob(text, tokenizer=tokenizer)
        skype_indices, tokens = [], []
        for i, token in enumerate(blob.tokens):
            tokens.append(token)
            if 'skype' in token.lower():
                skype_indices.append(i)

        # go through the words before and after skype words to identify
        # potential skype usernames.
        skype_usernames = []
        for i in skype_indices:
            jmin = max(i-self.skype_word_radius, 0)
            jmax = min(i+self.skype_word_radius+1, len(tokens))
            for j in range(jmin, i) + range(i+1, jmax):
                token = tokens[j]
                if regexps.SKYPE_USERNAME.match(token):

                    # this token is a valid skype username. Most skype
                    # usernames appear to be misspelled words. Word.spellcheck
                    # does not handle the situation of an all caps word very
                    # well, so we cast these to all lower case before checking
                    # whether the word is misspelled
                    if token.isupper():
                        token = token.lower()
                    word = textblob.Word(token)
                    suggestions = word.spellcheck()
                    corrected_word, score = suggestions[0]
                    if score < 0.5:
                        skype_usernames.append(token)

        # replace all skype usernames
        for skype_username in skype_usernames:
            text = text.replace(skype_username, self.skype_replacement)

        return text
