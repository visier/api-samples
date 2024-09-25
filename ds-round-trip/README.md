# Pay Transparency Analysis with Visier

## Overview

This example provides a framework for building custom machine learning solutions using Visier APIs. It is designed to help organizations meet the requirements of the **EU Pay Transparency Directive** by integrating people data and predictive analytics to:

- Analyze **gender pay gaps** and understand the factors that contribute to them.
- Identify objective criteria like **experience** and **education** that impact compensation.
- Visualize **adjusted pay gaps** and develop actionable **remediation plans**.
- Foster an **inclusive workplace culture** while minimizing compliance risks.

By leveraging this framework, organizations can customize their data pipeline and machine learning models to fetch, analyze, and visualize data. The insights gained enable informed, data-driven decisions to close pay gaps and ensure fair compensation practices.

## Local Environment Setup

To get started with this example on your local machine, follow these steps:

### 1. Application Setup
- For this example, we require the following attributes: `EmployeeID`, `isFemale`, `Employee.Internal_Job_Experience`, `Highest_Education_Level_Achieved`, `Internal_Experience`, `External_Experience`, and `Market_Direct_Compensation` to conduct the analysis. If any of these attributes are missing from the tenant project schema and analytic model, [create a new attributes](https://docs.visier.com/developer/Tutorials/analytic-model/enhance-analytic-model.htm) under the `Employee` analytic object.
- [Obtain an APIKey](https://docs.visier.com/developer/Studio/solution%20settings/api-key-generate.htm)
- The output files will contain 3 columns: `EmployeeID`, `EventDate`, and `Market_Direct_Compensation`. The first two are key attributes, Ensure all non-key attributes (in this case, `Market_Direct_Compensation`) are unmapped in the primary data category mappings.

### 2. Local Machine Setup
1. **Install Python**  
   Download and install Python 3.10 or above from [here](https://www.python.org/downloads/). Confirm the installation by running:
    ```bash
    python3 -V
    ```

2. **Install Dependencies**  
    Navigate to the directory and install the required Python packages by running the following command in your terminal or virtual environment:
    ```bash
    pip install -r requirements.txt
    ```

3. **Set Up Credentials**  
Open the `.env` file and update it with your Visier API credentials to ensure successful API integration.

### 3. Start the example
You are now ready to begin your machine learning exploration! Open the **main.ipynb** notebook and start working on analyzing pay gaps and creating actionable insights.
