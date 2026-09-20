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

"""Test utility to generate random tenants in multiple batches."""

import json
import random
import string
from dotenv import load_dotenv
from visier_api_administration.api.tenants_v1_api import TenantsV1Api
from app import get_template, load_tenant_data, build_request_body, add_tenants

NUM_BATCHES = 10
NUM_TENANTS_PER_BATCH = 200

def generate_random_tenant():
    code = ''.join(random.choices(string.digits, k=12))
    name = f"Customer {''.join(random.choices(string.ascii_uppercase, k=3))}, {random.choice(['Inc.', 'Ltd.', 'LLC.'])}"
    return {"code": code, "name": name}

def write_random_tenant_data():
    tenants = [generate_random_tenant() for _ in range(NUM_TENANTS_PER_BATCH)]
    with open('data/tenants.json', 'w') as f:
        json.dump(tenants, f, indent=4)


if __name__ == '__main__':
    template = get_template()
    load_dotenv()
    tenant_api = TenantsV1Api()

    for i in range(NUM_BATCHES):
        write_random_tenant_data()
        tenant_data = load_tenant_data()
        request_json = build_request_body(template, tenant_data)
        response = add_tenants(tenant_api, request_json)
        print(f"Generated batch {i+1} of {NUM_BATCHES} with {NUM_TENANTS_PER_BATCH} tenants each.")