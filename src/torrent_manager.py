from torrent_configuration import TorrentConfiguration
import qbittorrentapi


class TorrentManager:
    def __init__(self):
        self.config = TorrentConfiguration()
        self.client = self._create_client()

    def _create_client(self):
        return qbittorrentapi.Client(
            host=self.config.host,
            port=self.config.port,
            username=self.config.username,
            password=self.config.password,
        )
