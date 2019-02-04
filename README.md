# jellyfin-collections

## Requires

* Python3.6 or greater
* A Jellyfin api key
  * Admin panel -> Advanced -> Security

## Usage

* Install required libraries
  * `pip install -r requirements.txt`
* Edit `create-collections.py` with required information
  * api keys and server URL
* run `python create-collections.py`

####Note:
Getting the initial library data can take a while, especially if you have a spotty connection or an extremely large library (>10,000 entries). Use the `--initial-timeout` flag to override the default behavior of 500 seconds if something's going wrong.

Example:
```bash
python create-collections.py --initial-timeout 1000
```
