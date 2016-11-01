import pytest
from notifications_utils.renderers import (
    PassThrough, HTMLEmail, PlainTextEmail, SMSMessage, SMSPreview
)
from notifications_utils.formatters import (
    unlink_govuk_escaped, linkify, notify_markdown, prepare_newlines_for_markdown
)


@pytest.mark.parametrize(
    "url", [
        "http://example.com",
        "http://www.gov.uk/",
        "https://www.gov.uk/",
        "http://service.gov.uk",
        "http://service.gov.uk/blah.ext?q=a%20b%20c&order=desc#fragment",
        pytest.mark.xfail("http://service.gov.uk/blah.ext?q=one two three"),
    ]
)
def test_makes_links_out_of_URLs(url):
    link = '<a style="word-wrap: break-word;" href="{}">{}</a>'.format(url, url)
    assert (linkify(url) == link)
    assert link in HTMLEmail()(url)


@pytest.mark.parametrize(
    "url", [
        "example.com",
        "www.example.com",
        "ftp://example.com",
        "mailto:test@example.com",
        "http://service.gov.uk/register/<span class='placeholder'>((token))</span>"
    ]
)
def test_doesnt_make_links_out_of_invalid_urls(url):
    assert url == linkify(url)


@pytest.mark.parametrize(
    "url, expected_html", [
        (
            """https://example.com"onclick="alert('hi')""",
            """<a style="word-wrap: break-word;" href="https://example.com%22onclick=%22alert%28%27hi%27%29">https://example.com"onclick="alert('hi')</a>"""  # noqa
        ),
        (
            """https://example.com"style='text-decoration:blink'""",
            """<a style="word-wrap: break-word;" href="https://example.com%22style=%27text-decoration:blink%27">https://example.com"style='text-decoration:blink'</a>"""  # noqa
        ),
    ]
)
def test_URLs_get_escaped(url, expected_html):
    assert linkify(url) == expected_html
    assert expected_html in HTMLEmail()(url)


def test_HTML_template_has_URLs_replaced_with_links():
    assert (
        '<a style="word-wrap: break-word;" href="https://service.example.com/accept_invite/a1b2c3d4">'
        'https://service.example.com/accept_invite/a1b2c3d4'
        '</a>'
    ) in HTMLEmail()('''
        You’ve been invited to a service. Click this link:
        https://service.example.com/accept_invite/a1b2c3d4

        Thanks
    ''')


def test_preserves_whitespace_when_making_links():
    assert (
        '<a style="word-wrap: break-word;" href="https://example.com">'
        'https://example.com'
        '</a>\n'
        '\n'
        'Next paragraph'
    ) == linkify(
        'https://example.com\n'
        '\n'
        'Next paragraph'
    )


def test_add_spaces_after_single_newlines_so_markdown_converts_them():
    converted = prepare_newlines_for_markdown(
        'Paragraph one\n'
        '\n'
        'Paragraph two has linebreaks\n'
        'This is the second line\n'
        'The third has 2 spaces after it  \n'
        'And this is the fourth\n'
        '\n'
        'Next paragraph'
    )
    assert converted == (
        'Paragraph one\n'
        '\n'
        'Paragraph two has linebreaks  \n'
        'This is the second line  \n'
        'The third has 2 spaces after it  \n'
        'And this is the fourth\n'
        '\n'
        'Next paragraph'
    )
    assert notify_markdown(converted) == (
        '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">'
        'Paragraph one'
        '</p>'
        '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">'
        'Paragraph two has linebreaks<br/>'
        'This is the second line<br/>'
        'The third has 2 spaces after it<br/>'
        'And this is the fourth'
        '</p>'
        '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">'
        'Next paragraph'
        '</p>'
    )


@pytest.mark.parametrize(
    "template_content,expected", [
        ("gov.uk", u"gov.\u200Buk"),
        ("GOV.UK", u"GOV.\u200BUK"),
        ("Gov.uk", u"Gov.\u200Buk"),
        ("https://gov.uk", "https://gov.uk"),
        ("https://www.gov.uk", "https://www.gov.uk"),
        ("www.gov.uk", "www.gov.uk"),
        ("gov.uk/register-to-vote", "gov.uk/register-to-vote"),
        ("gov.uk?q=", "gov.uk?q=")
    ]
)
def test_escaping_govuk_in_email_templates(template_content, expected):
    assert unlink_govuk_escaped(template_content) == expected
    assert PlainTextEmail()(template_content) == expected
    assert expected in HTMLEmail()(template_content)


@pytest.mark.parametrize(
    "prefix, body, expected", [
        ("a", "b", "a: b"),
        (None, "b", "b"),
    ]
)
def test_sms_message_adds_prefix(prefix, body, expected):
    assert SMSMessage(prefix=prefix)(body) == expected
    assert SMSPreview(prefix=prefix)(body) == expected


def test_sms_preview_adds_newlines():
    assert SMSPreview()("""
        the
        quick

        brown fox
    """) == "the<br>        quick<br><br>        brown fox"


class TestNotifyMarkdown():

    def test_block_code(self):
        assert notify_markdown('```\nprint("hello")\n```') == 'print("hello")'

    def test_block_quote(self):
        assert notify_markdown('^ inset text') == (
            '<blockquote '
            'style="Margin: 0 0 20px 0; border-left: 10px solid #BFC1C3;'
            'padding: 15px 0 0.1px 15px; font-size: 19px; line-height: 25px;'
            '">'
            '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">inset text</p>'
            '</blockquote>'
        )

    def test_level_1_header(self):
        assert notify_markdown('# heading') == (
            '<h2 style="Margin: 0 0 20px 0; padding: 0; font-size: 27px; '
            'line-height: 35px; font-weight: bold; color: #0B0C0C;">'
            'heading'
            '</h2>'
        )

    def test_level_2_header(self):
        assert notify_markdown(
            '## inset text'
        ) == (
            '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">inset text</p>'
        )

    def test_hrule(self):
        assert notify_markdown('a\n\n***\n\nb') == (
            '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">a</p>'
            '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">b</p>'
        )
        assert notify_markdown('a\n\n---\n\nb') == (
            '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">a</p>'
            '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">b</p>'
        )

    def test_ordered_list(self):
        assert notify_markdown(
            '1. one\n'
            '2. two\n'
            '3. three\n'
        ) == (
            '<ol style="Margin: 0 0 20px 0; padding: 0; list-style-type: decimal;">'
            '<li style="Margin: 5px 0 5px 20px; padding: 0; display: list-item; font-size: 19px; '
            'line-height: 25px; color: #0B0C0C;">one</li>'
            '<li style="Margin: 5px 0 5px 20px; padding: 0; display: list-item; font-size: 19px; '
            'line-height: 25px; color: #0B0C0C;">two</li>'
            '<li style="Margin: 5px 0 5px 20px; padding: 0; display: list-item; font-size: 19px; '
            'line-height: 25px; color: #0B0C0C;">three</li>'
            '</ol>'
        )

    def test_unordered_list(self):
        assert notify_markdown(
            '* one\n'
            '* two\n'
            '* three\n'
        ) == (
            '<ul style="Margin: 0 0 20px 0; padding: 0; list-style-type: disc;">'
            '<li style="Margin: 5px 0 5px 20px; padding: 0; display: list-item; font-size: 19px; '
            'line-height: 25px; color: #0B0C0C;">one</li>'
            '<li style="Margin: 5px 0 5px 20px; padding: 0; display: list-item; font-size: 19px; '
            'line-height: 25px; color: #0B0C0C;">two</li>'
            '<li style="Margin: 5px 0 5px 20px; padding: 0; display: list-item; font-size: 19px; '
            'line-height: 25px; color: #0B0C0C;">three</li>'
            '</ul>'
        )

    def test_paragraphs(self):
        assert notify_markdown(
            'line one\n'
            'line two\n'
            '\n'
            'new paragraph'
        ) == (
            '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">line one\n'
            'line two</p>'
            '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">new paragraph</p>'
        )

    def test_table(self):
        assert notify_markdown(
            'col | col\n'
            '----|----\n'
            'val | val\n'
        ) == (
            ''
        )

    def test_autolink(self):
        assert notify_markdown(
            'http://example.com'
        ) == (
            '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">http://example.com</p>'
        )

    def test_codespan(self):
        assert notify_markdown(
            'variable called `thing`'
        ) == (
            '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; '
            'color: #0B0C0C;">variable called thing</p>'
        )

    def test_double_emphasis(self):
        assert notify_markdown(
            'something **important**'
        ) == (
            '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">something important</p>'
        )

    def test_emphasis(self):
        assert notify_markdown(
            'something *important*'
        ) == (
            '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">something important</p>'
        )

    def test_image(self):
        assert notify_markdown(
            '![alt text](http://example.com/image.png)'
        ) == (
            ''
        )

    def test_link(self):
        assert notify_markdown(
            '[Example](http://example.com)'
        ) == (
            '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; '
            'color: #0B0C0C;">Example: http://example.com</p>'
        )

    def test_strikethrough(self):
        assert notify_markdown(
            '~~Strike~~'
        ) == (
            '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">Strike</p>'
        )

    def test_footnotes(self):
        # Can’t work out how to test this
        pass