import requests
import json
from os import environ
import cobra
import yamllint
from yamllint.config import YamlLintConfig

api_endpoint = 'https://api.github.com/graphql'
api_token = environ['GH_TOKEN']
header_auth = {'Authorization': 'token %s' % api_token}
model_filename = 'model.yml'

def gem_repositories():
    json_request = {"query" : "{ search(type: REPOSITORY, query: \"\"\"fork:true topic:standard-GEM\"\"\", first: 100) { repos: edges { repo: node { ... on Repository { nameWithOwner } } } } }" }
    r = requests.post(url=api_endpoint, json=json_request, headers=header_auth)
    json_data = json.loads(r.text)['data']['search']['repos']
    gem_repositories = map(lambda x: x['repo']['nameWithOwner'], json_data)
    filtered_repositories = filter(lambda x: 'standard-GEM' not in x, gem_repositories)
    return filtered_repositories

def releases(nameWithOwner):
    owner, repo =  nameWithOwner.split('/')
    json_request = { "query": "{ repository(owner: \"%s\", name: \"%s\") { releases(last: 10) { edges { node { tagName } } } } }" % (owner, repo) }
    r = requests.post(url=api_endpoint, json=json_request, headers=header_auth)
    json_data = json.loads(r.text)['data']['repository']['releases']['edges']
    release_tags = list(map(lambda x: x['node']['tagName'], json_data))
    if not release_tags:
        return []
    return release_tags + ['develop']

def matrix():
    m = list(map(lambda g: { 'gem': g }, gem_repositories()))
    print(json.dumps({"include": m }))

def gem_follows_standard(nameWithOwner, release, version):
    repo_standard = requests.get('https://raw.githubusercontent.com/{}/{}/.standard-GEM.md'.format(nameWithOwner, release))
    if repo_standard.status_code ==  404:
        return False
    repo_standard = repo_standard.text
    raw_standard = requests.get('https://raw.githubusercontent.com/MetabolicAtlas/standard-GEM/{}/.standard-GEM.md'.format(version)).text
    import difflib
    the_diff = difflib.ndiff(repo_standard, raw_standard)
    return True

def validate(nameWithOwner):
    owner, model = nameWithOwner.split('/')
    data = {}
    data[nameWithOwner] = []
    for model_release in releases(nameWithOwner):
        release_data = {}
        for standard_version in releases('MetabolicAtlas/standard-GEM'):
            print("Release: {} | Standard: {}".format(model_release, standard_version))
            is_standard = gem_follows_standard(nameWithOwner, model_release, standard_version)
            tests = {}
            if is_standard:
                response = requests.get('https://raw.githubusercontent.com/{}/{}/model/{}.yml'.format(nameWithOwner, model_release, model))
                with open(model_filename, 'w') as file:
                    file.write(response.text)

                print('  validate YAML with yamllint')
                is_valid_yaml = False
                try:
                    conf = YamlLintConfig('{extends: default, rules: {line-length: disable}}')
                    with open(model_filename, 'r') as file:
                        gen = yamllint.linter.run(file, conf)
                    is_valid_yaml = len(list(gen)) == 0
                except Exception as e:
                    print(e)
                finally:
                    tests['yamllint'] = { yamllint.__version__ : is_valid_yaml }

                print('  load yml with cobrapy')
                is_valid_cobrapy = False
                try:
                    cobra.io.load_yaml_model(model_filename)
                    is_valid_cobrapy = True
                except Exception as e:
                    print(e)
                finally:
                    tests['cobrapy-yaml-load'] = { cobra.__version__ : is_valid_cobrapy }
            release_data = { 'standard-GEM' : [ { standard_version : is_standard }, { 'tests' : tests} ] }
        data[nameWithOwner].append({ model_release: release_data })
    with open('results/{}_{}.json'.format(owner, model), 'w') as output:
        output.write(json.dumps(data, indent=2, sort_keys=True))
