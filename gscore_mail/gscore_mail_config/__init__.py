"""gscore_mail StringConfig。"""

from gsuid_core.data_store import get_res_path
from gsuid_core.utils.plugins_config.gs_config import StringConfig

from .config_default import CONFIG_DEFAULT

CONFIG_PATH = get_res_path("gscore_mail") / "gscore_mail_config.json"

mail_config = StringConfig(
    "gscore_mail",
    CONFIG_PATH,
    CONFIG_DEFAULT,
)
