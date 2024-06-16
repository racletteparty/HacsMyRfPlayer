from dataclasses import dataclass


@dataclass
class GenericJsonConfig:
    info_type: str
    json_path: str
    mask: int | None
    offset: int | None


@dataclass
class GenericJsonDevice:
    config: dict[str, GenericJsonConfig]

    def get_values(self, raw_packet: JsonPacketType):
        values = {}
        for key, config in self.config.items():
            if raw_packet["frame"]["header"]["infoType"] == config.info_type:
                expr = parse(config.json_path)
                first_match = next(expr.find(raw_packet), None)
                if first_match:
                    value: str = first_match.value
                    if config.mask:
                        value = str(int(value) & config.mask)
                    if config.offset:
                        value = str(int(value) >> config.offset)
                    values[key] = value
        return values

class TemperatureSensor:

    def get_values(self, raw_packet: JsonPacketType):
        return {
            "temperature": raw_packet["frame"]["infos"][""]
        }
