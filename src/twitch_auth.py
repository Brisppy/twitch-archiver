# This file contains functions related to generating and validating twitch authentication tokens.

import requests

# Takes two arguments, CLIENT_ID and CLIENT_SECRET and calls the Twitch API to generate and store a new token.
# Returns a new OAUTH token
def GenerateTwitchAuthToken(CLIENT_ID, CLIENT_SECRET):
    # Create the request body
    body = {'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'grant_type': 'client_credentials'}
    # Request a new token from Twitch
    try:
        r = requests.post('https://id.twitch.tv/oauth2/token', body)
        if r.status_code != 200:
            print('ERROR: Response other than 200 received.')
            print('ERROR:', r.text)
            return
    except requests.exceptions.RequestException as e:
        print('ERROR: Twitch API call failed.')
        print('ERROR:', e)
        return
    # Return just the token
    return r.json()['access_token']


def ValidateTwitchAuthToken(OAUTH_TOKEN):
    headers = {'Authorization': 'Bearer ' + OAUTH_TOKEN}
    try:
        r = requests.get('https://id.twitch.tv/oauth2/validate', headers=headers)
        if r.status_code != 200:
            print('ERROR: Token was not validated by Twitch.')
            print('ERROR:', r.text)
            return 'Invalid'
    except requests.exceptions.RequestException as e:
        print('ERROR: Twitch API call failed.')
        print('ERROR:', e)
        return
    # Return remaining duration of token
    return r.json()['expires_in']
