from docstub._config import Config


class Test_Config:
    def test_from_default(self):
        config = Config.from_default()
        assert len(config.types) > 0
        assert len(config.type_prefixes) > 0
        assert len(config.type_nicknames) > 0
