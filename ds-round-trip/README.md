# Pay Transparency Analysis with Visier

This example provides a framework for building custom machine learning solutions using Visier APIs. It is designed to help organizations meet the requirements of the **EU Pay Transparency Directive** by integrating people data and predictive analytics to:

- Analyze **gender pay gaps** and understand the factors that contribute to them.
- Identify objective criteria like **experience** and **education** that impact compensation.
- Visualize **adjusted pay gaps** and develop actionable **remediation plans**.
- Foster an **inclusive workplace culture** while minimizing compliance risks.

By leveraging this framework, organizations can customize their data pipeline and machine learning models to fetch, analyze, and visualize data. The insights gained enable informed, data-driven decisions to close pay gaps and ensure fair compensation practices.

## Local Environment Setup

To get started with this example on your local machine, follow these steps.

### Visier Setup
- In your Visier tenant, the Employee subject must have the following attributes. If you don't have these attributes, create them in a project. For more information, see [Understand Visier's Analytic Model](https://docs.visier.com/developer/Default.htm#cshid=1035).
  - `EmployeeID`
  - `External_Experience`
  - `Highest_Education_Level_Achieved`
  - `Internal_Experience`
  - `Internal_Job_Experience`
  - `isFemale`
  - `Market_Direct_Compensation`
- In a project in Visier, in **Mappings**, select the primary data category and make sure that `Market_Direct_Compensation` is unmapped. In this example's CSV output, `Market_Direct_Compensation` is a non-key column, so it must be unmapped. The other attributes can be mapped or unmapped. For more information, see [Mappings](https://docs.visier.com/developer/Default.htm#cshid=1021).
- Retrieve your tenant's API key. For more information, see [Generate an API Key](https://docs.visier.com/developer/Default.htm#cshid=1045).

### Local Machine Setup
**Install Python**  
   Download and install [Python 3.10 or above](https://www.python.org/downloads/). To confirm the installation, run the following command:
    ```bash
    python3 -V
    ```

**Install Dependencies**  
    To install the required Python packages, navigate to the directory and run the following command in your terminal or virtual environment:
    ```bash
    pip install -r requirements.txt
    ```

**Provide Credentials**  
Update your Visier API credentials in the `.env` file.

### Start Analyzing
You're ready to begin your machine learning experience! Open **main.ipynb** to start analyzing pay gaps and create actionable insights.
