import logging
import sys
import time
import urllib
from typing import Dict
from typing import List
from typing import Union

import requests
import tmdbsimple as tmdb
from requests.models import Response

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s | %(funcName)s | %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S',
)

# Adjust the three variables below as needed.
# A Jellyfin API key can be generated by going to the admin page,
# Advanced -> Security
# You must have an account with themoviedb to get an API key
# https://developers.themoviedb.org/3/getting-started/introduction

server_url = "http://localhost/emby:8096"
jellyfin_api_key = "foo"
tmdb.API_KEY = "bar"

headers = {'X-Emby-Token': jellyfin_api_key}
requests_timeout = 5


class MovieDataError(Exception):
    pass


class NoDataError(Exception):
    pass


def get_library_data() -> Response:
    logging.info("Getting initial data from Jellyfin.")
    logging.info("If you have a large library, this can take a while. Please be patient.")
    try:
        library = requests.get(
            f"{server_url}/Items?Recursive=true&IncludeItemTypes=Movie",
            headers=headers,
            timeout=500
        )
        library.raise_for_status()
    except (
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError,
            requests.exceptions.ReadTimeout
    ) as e:
        logging.fatal(f'Cannot connect to Jellyfin server! Error: {e}')
        sys.exit(1)

    logging.info("Successfully authenticated with jellyfin!")
    logging.info("Beginning to search for collection info!")
    return library


def check_single_movie(movie: Dict, library_collection: Dict) -> Dict:
    jellyfin_id = movie.get('Id')
    tmdb_id = movie.get('ProviderIds').get('Tmdb')
    # sleep to avoid rate limit
    time.sleep(.5)

    if not tmdb_id:
        # There's no entry, so don't bother asking tmdb.
        raise NoDataError

    try:
        movie_info = tmdb.Movies(tmdb_id).info()
        logging.info(f'Checking {movie.get("Name")}')

        # If a movie is in a collection, it gets added to a local dictionary
        # to be used later
        if movie_info.get('belongs_to_collection'):
            collection_id = movie_info['belongs_to_collection'].get('id')
            raw_collection_name = movie_info['belongs_to_collection'].get('name')

            logging.info(f' ┗ Found matching collection: {raw_collection_name}!')
            # URL encode the collection name for the jellyfin api
            collection_name = urllib.parse.quote(raw_collection_name)

            # Checks if a collection already exists in the dictionary.  If so,
            # it adds it to the existing. If not, it creates a new entry with
            # the human readable name, the URL encoded name, and the jellyfin
            # object IDs of each movie that belongs there

            if library_collection.get(collection_id):
                library_collection[collection_id]["ids"].append(jellyfin_id)
            else:
                library_collection[collection_id] = {
                    "Name": collection_name,
                    "raw_name": raw_collection_name,
                    "ids": [jellyfin_id]
                }

        return library_collection

    except Exception as e:
        raise MovieDataError(e)


def write_errors_to_disk(errors: List) -> None:
    # Write the errors list to a log file for manual review
    with open("collection-errors.txt", "w") as errorFile:
        for error in errors:
            errorFile.write(error + '\n')


def get_collection_data(library: Response) -> Union[Dict, Dict]:

    collections = {}
    errors = []
    # Loop through movies, looking them up at themoviedb.
    for movie in library.json()['Items']:
        try:
            collections = check_single_movie(movie, collections)

        except MovieDataError as e:
            # If any errors occur, add them to the errors list
            errors.append(f'{str(movie.get("Name"))} - {e}')
            logging.warning(f'Error on {movie.get("Name")} - {e}. Continuing.')
            continue

        except NoDataError:
            logging.warning(f'No entry found for {movie.get("Name")} - continuing.')
            continue

    if errors:
        write_errors_to_disk(errors)

    logging.info('=' * 42)
    logging.info('=' * 42)
    logging.info("Data lookup complete!")
    logging.info("Starting to create collections...")
    return collections


def create_collections(collections: Dict) -> None:

    # Loop through the newly created dictionary, creating collections and items
    for collection, data in collections.items():
        # Only create a collection if it has more than 1 entry
        if len(data['ids']) > 1:
            # Create a collection
            logging.info(f"Creating {data['raw_name']}")
            requests.post(
                f"{server_url}/Collections?Name={data['Name']}",
                headers=headers,
                timeout=requests_timeout
            )

            library_collections = requests.get(
                f"{server_url}/Items?"
                f"Recursive=true"
                f"&IncludeItemTypes=BoxSet",
                headers=headers,
                timeout=requests_timeout
            ).json()['Items']

            try:
                # pulls out the ID of the jellyfin collection
                library_collection_id = [
                    x['Id'] for x in library_collections if x['Name'] == data['raw_name']
                ][0]

                # Adds movies to each collection
                requests.post(
                    f"{server_url}/Collections/{library_collection_id}/Items?"
                    f"Ids={','.join(data['ids'])}",
                    headers=headers,
                    timeout=requests_timeout
                )
                logging.info(f"Added movies to {data['raw_name']}")
            except Exception as e:
                logging.error(f"There was an error sorting: {data['raw_name']} - {e}")


def refresh_collection_metadata() -> None:
    # Finds ID of Collections library in jellyfin
    folders = requests.get(
        f"{server_url}/Library/MediaFolders",
        headers=headers,
        timeout=requests_timeout
    )

    folders.raise_for_status()

    folder_id = [
        x['Id'] for x in folders.json()['Items'] if x['Name'] == "Collections"
    ]
    folder_id = folder_id[0]
    logging.info('Forcing refresh of collection metadata...')
    # Triggers a refresh of the metadata in the collections library
    refresh = requests.post(
        f"{server_url}/Items/{folder_id}/Refresh?"
        f"Recursive=true&"
        f"MetadataRefreshMode=FullRefresh&"
        f"ImageRefreshMode=FullRefresh",
        headers=headers,
        timeout=requests_timeout
    )
    refresh.raise_for_status()
    logging.info('Metadata refresh successfully started!')
    logging.info('\n\n\tThanks for waiting; all done!\n')


def main() -> None:
    library = get_library_data()
    collection_data = get_collection_data(library)
    create_collections(collection_data)
    refresh_collection_metadata()


if __name__ == '__main__':
    main()
