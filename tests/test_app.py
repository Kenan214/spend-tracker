import app


class TestEscapeMarkdownDollars:
    def test_escapes_every_dollar_sign(self):
        assert app.escape_markdown_dollars("over $30 totaling $2,873.46") == r"over \$30 totaling \$2,873.46"

    def test_no_dollar_signs_is_unchanged(self):
        assert app.escape_markdown_dollars("no dollars here") == "no dollars here"

    def test_empty_string(self):
        assert app.escape_markdown_dollars("") == ""
