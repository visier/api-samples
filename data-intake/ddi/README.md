# Direct Data Intake API
The Direct Data Intake (DDI) API is suitable for users whose data requires no additional transformations to load into Visier. Because the data is suitable to load into Visier without transformation, the data load process is "direct". In your data source files, the column names must exactly match the names of objects in Visier that you want to load data into.

If only some of your data is suitable to load directly, you can use a combination of the DDI API and other data transfer methods to send all of your data to Visier. For more information about sending data to Visier, see [Data In](https://docs.visier.com/developer/Studio/data/data-in-home.htm).

## Data Intake Modes
When using the DDI API, you must configure the data intake mode. This configuration defines the relationship between the DDI data category and any other data transfer methods that you use to send data to Visier.

To view a diagram outlining the data intake modes, see
![Three Direct Data Intake API Load Modes](/assets/images/load-options.png)
* **Primary**: All Visier objects are loaded using the DDI API. Before using the DDI API, the Visier tenant doesn't have an existing data category, that is, the tenant doesn’t contain customer data yet. Primary is the default configuration.
* **Supplemental**: The Visier tenant contains some customer data that was loaded through a method other than the DDI API. With Supplemental mode, you can use the DDI API to load data for objects that don't yet contain data.
* **Extension**: The Visier tenant contains customer data that was loaded through a method other than the DDI API and you want to load additional data for already-loaded objects. To use Extension mode, your data load actions must meet the following criteria:
    * The object is primarily loaded through other data transfer methods (not DDI API).
    * The data transfer methods, DDI API and otherwise, must not load the same properties on the object. For example, you cannot load EmployeeID with SFTP and then try to load EmployeeID with the DDI API.

### Examples
To understand which mode is applicable in which situations, consider the following scenarios.
* You are a new Visier customer and you want to integrate Visier into an existing data flow that extracts from operational systems, cleanses, and deduplicates before loading the data into a data warehouse. Because your source data has been transformed and is at the appropriate level of granularity, it is straightforward to add simple column name mappings to match the data load schema of the analytic objects in Visier. For this reason, you want to load all Visier-relevant data using the Direct Data Intake API. In this case, the data intake mode is **Primary**.
* You are an existing Visier customer with an established data provisioning process for loading the core analytic objects, such as `Employee`, `Employment_Start`, and `Employee_Exit`. You recently made the decision to expand your Visier platform capabilities by adding Talent Acquisition (TA). Your operational TA application already provisions data into an existing and extensible ETL process. To ensure you don't have to replicate the ETL-system configuration in Visier, you choose to load the TA data using the Direct Data Intake API. Because you're using the API to load objects that don't already have data, you are supplementing the primary data load process in Visier, and the appropriate data intake mode is **Supplemental**.
* You are an existing Visier customer with an established data provisioning process for loading the core analytic objects, such as `Employee`, `Employment_Start`, and `Employee_Exit`. Your data science team recently trained a machine learning model that can predict Risk of Exit and you want to add the predictions as new properties on the Employee object in Visier. You first add the Risk of Exit property to the `Employee` object in Visier, and then decide to integrate Visier into your data pipeline so that the predictions are written back to Visier using the Direct Data Intake API. Because your `Employee` data is coming from two sources (your established data provisioning process for most of your `Employee` data and the DDI API for the Risk of Exit employee data), the data intake mode is **Extension**.

## Samples
* [Extension Table](extension-table/jupyter/name-rank-sample.ipynb) provides a Jupyter notebook sample showing how query, extend, and write data back to Visier.
