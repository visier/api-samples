# Copyright 2024 Visier Solutions Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from datetime import datetime, timezone
import json
from dotenv import load_dotenv
from dynaconf import Dynaconf
from jinja2 import Environment, StrictUndefined
from visier_api_administration.api.tenants_v1_api import TenantsV1Api
from visier_api_administration.models import BatchTenantProvisionAPIDTO


# Overkill for this example, but it's a good practice to use a configuration management tool.
# In this case, we're loading the request template for making bulk tenant creation requests.
global_conf = Dynaconf(settings_files=['./templates/tenants.toml'])
for conf in global_conf:
    if conf.lower() == 'bulk_create_tenants':
        template = global_conf[conf].create

# Load the tenant definitions.
with open('./data/tenants.json', 'r')  as data_file:
    tenants = json.load(data_file)

# Render the request by resolving the template with the tenant definitions.
environment = Environment(undefined=StrictUndefined)
provision_date = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
request_json = environment.from_string(template).render(tenants=tenants,
                                                   provision_date=provision_date)

# Get ready to call the API
load_dotenv()
tenant_api = TenantsV1Api()

request = BatchTenantProvisionAPIDTO.from_json(request_json)
response = tenant_api.add_tenants(request)
print(response)