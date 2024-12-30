import re

#############################################################################
# Cubari-Flavoured Markdown
#############################################################################
# This module handles "Cubari-Flavoured Markdown". CFM is a very dumbed down
# set of supported tags (and parsing) in order to safely inject styling to
# descriptions in things like gists.

# The supported tags are:
# - URLs
# - Headers (atx-style. Parsed into span blocks with font-size. Capped at 4 levels)
# - Inline emphasis (bold, italics)
# - Inline code

# This utility also handles stripping HTML tags by replacing ", ', <, > with
# their escaped equivalents.

#############################################################################
# Example
#############################################################################
# text = """
# [This is a link](http://example.net/).
# Another inline link [here](http://example.net/).
# One more link for good measure: http://example.net/
# # Header 1
# ## Header 2
# ### Header 3
# #### Header 4
# ##### Header 5 - Capped Size
# *some italics* and _more italics_
# **some bold** and __more bold__
# `code`
# """

# result = parse_html(text)

# print(result)
# | <a href="http://example.net/">This is a link</a>.
# | Another inline link <a href="http://example.net/">here</a>.
# | One more link for good measure: <a href="http://example.net/">http://example.net/</a>
# | <span style="font-size: 1.8em;">Header 1</span>
# | <span style="font-size: 1.7em;">Header 2</span>
# | <span style="font-size: 1.6em;">Header 3</span>
# | <span style="font-size: 1.5em;">Header 4</span>
# | <span style="font-size: 1.5em;">Header 5 - Capped Size</span>
# | <em>some italics</em> and <em>more italics</em>
# | <strong>some bold</strong> and <strong>more bold</strong>
# | <code>code</code>


def _convert_crlf(input_str: str) -> str:
    return input_str.encode().replace(b"\r\n", b"\n").decode("utf-8")


def _parse_links(input_str: str) -> str:
    input_str = re.sub(
        r"\[(.+?)\]\((https?:\/\/[-a-zA-Z0-9._~:/?#@!$&()*+,;=%']+)\)",
        r'<a href="\2" target="_blank" rel="nofollow noreferrer noopener">\1</a>',
        input_str,
        flags=re.MULTILINE|re.IGNORECASE,
    )
    return re.sub(
        r"(?<!href=\")(https?:\/\/[-a-zA-Z0-9._~:/?#@!$&()*+,;=%']+)",
        r'<a href="\1" target="_blank" rel="nofollow noreferrer noopener">\1</a>',
        input_str,
        flags=re.MULTILINE|re.IGNORECASE,
    )

def _parse_headers(input_str: str) -> str:
    search = re.finditer(r"^(#{1,5}) +(.+)[# ]?$", input_str, re.MULTILINE)
    for i in search:
        h = 2 - (min(len(i.group(1)) + 1, 5) / 10)
        input_str = re.sub(
            i.group(),
            f'<span style="font-size: {h}em;">{i.group(2)}</span>',
            input_str,
        )
    return input_str

#Checks whether a string contains a plain non-quoted URL, mainly to later avoid <a herf> fields.
#Example:
#    Returns 'true' for: http://example.nonexistant 
#    Returns 'false' for: "http://example.nonexistnat"
def _is_plain_url(input_str: str) -> bool:
    return re.search(r"(?<!\")(https?:\/\/[-a-zA-Z0-9._~:/?#@!$&()*+,;=%']+)(?!\")", input_str) != None

def _parse_strong_emphasis(input_str: str) -> str:
    output_str="\n"

    #Iterates over every line and checks for URLs. Applies substition by regex only if there aren't any.
    #This is necessiary as some URLs can be misinterpreted as markdown text, which promptly messes up the outputed HTML (as was seen here: https://tomo.fukai20.com). 

    #If anyone knows how to do the following purely with a regex, go ahead. I couldn't figure it out
    # -Night

    for l in input_str.splitlines():
        if (not _is_plain_url(l)):
            output_str+=re.sub(
                    r"(?<!\\)\*\*(\w.*?)(?<!\\)\*\*(?![\\,\"])|(?<!\\)\_\_(\w.*?)(?<!\\)\_\_",
                    r"<strong>\1\2</strong>",
                    l,
                )+"\n"
        else:
            output_str+=l + "\n"    
    return output_str

def _parse_em_emphasis(input_str: str) -> str:
    output_str = ""

    #Iterates over every line and checks for URLs. Applies substition by regex only if there aren't any.
    #This is necessiary as some URLs can be misinterpreted as markdown text, which promptly messes up the outputed HTML (as was seen here: https://tomo.fukai20.com). 

    #If anyone knows how to do the following purely with a regex, go ahead. I couldn't figure it out. 
    # -Night

    for l in input_str.splitlines():
        if (not _is_plain_url(l)):
            output_str+=re.sub(
                    r"(?<![\\,\"])(?<!\*)\*(\w.*?)(?<!\\)\*(?![\\,\",*])|(?<![\\,\"])(?<!\_)_(?!_)(\w.*?)(?<![\\,\"])_(?!\_)",
                    r"<em>\1\2</em>",
                    l,
                )+"\n"
        else:
           output_str+=l + "\n"
    return output_str

def _parse_code(input_str: str) -> str:
    return "\n".join(
        re.sub(r"`(.+?)`", r"<code>\1</code>", l)
        for l in input_str.splitlines()
    )


def _escape(input_str: str) -> str:
    escapes = [
        ["&", "&amp;"],
        ['"', "&quot;"],
        ["'", "&#39;"],
        ["<", "&lt;"],
        [">", "&gt;"],
    ]

    intermediate_escape = input_str

    for seq, esc in escapes:
        intermediate_escape = intermediate_escape.replace(seq, esc)

    return intermediate_escape


def parse_html(input_str: str) -> str:
    parsers = [
        _convert_crlf,
        _escape,
        _parse_links,
        _parse_headers,
        _parse_strong_emphasis,
        _parse_em_emphasis,
        _parse_code,
    ]

    intermediate_parse_result = input_str

    for parser in parsers:
        intermediate_parse_result = parser(intermediate_parse_result)
    return intermediate_parse_result
