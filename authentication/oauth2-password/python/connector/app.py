# Copyright 2023 Visier Solutions Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Example python program to demonstrate the use of the Visier Python Connector
"""

from dotenv import dotenv_values
from visier.connector import VisierSession, make_auth
from visier.api import ModelApiClient

env_creds = dotenv_values()
auth = make_auth(env_values=env_creds)

with VisierSession(auth) as s:
    # Once conected, create the appropriate API client
    model_client = ModelApiClient(s)

    # Execute a model API
    members = model_client.get_members("Employee", "Gender")
    print(members.json())
