---
title: "Custom operation generation"
slug: custom-operation-generation
source: https://help.paperlessparts.com/s/article/custom-operation-generation
topic: "Part Analysis & Interrogation"
captured: 2026-06-19
---

# Custom operation generation

> Source: https://help.paperlessparts.com/s/article/custom-operation-generation  
> Topic: Part Analysis & Interrogation

In this article we will discuss how you can use geometric and/or user inputted information to dynamically generate operations for a part in a **custom process**. Let's first quickly review how our generic process works for comparison.

For each process, you have a list of *operation definitions* that will be generated for every part that the process is applied to:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5e9dd31304286364bc98a97b/file-kRFjZwpD3p.png)Additionally, you can apply logic to tell the system to generate operations only if the part is an assembly (the green ASSEMBLY flag) or only if the part is the root component for the quote item (the orange PER QUOTE ITEM flag). As many manufacturing operations are rigid, this more straightforward approach is usually sufficient to accomplish operation generation and/or routing needs. However, no two manufacturers are the same, and some operations have more conditional applications and formatting. This is where using a *custom process* can come in handy.

#### How It Works

A custom process consists of a list of allowed operations and a snippet of code that is responsible for generating these operations when the process is applied to a part. The code snippet works almost exactly like regular operation-level P3L, but instead of outputting a PRICE and DAYS, the program is instead responsible for outputting a list of operations to apply to the part. There are two new functions available to you from within process-level P3L:

`get_allowed_operations() -> P3LList`

This returns a P3LList of all the string names of the operations you have marked as allowed for the process. This also can act as an an iterator function. We will see below how you can use this function to replicate our generic process functionality.

`generate_operation(requested_op_def_name: str, custom_name: Optional[str] = None, operation_properties: Optional[dict] = None)`

This is the workhorse function for process-level P3L. As the name suggests, this function will generate an operation based off of the operation definition name you have inputted as the first argument. You can also specify a **custom_name** for this operation. If no custom name is specified, the name of the operation will match the name of the operation definition. NOTE: The usage of **set_operation_name** will override the **custom_name** passed in with this function. You also can optionally pass in a dictionary of key-value pairs to the operation that can be accessed from within the operation-level P3L using the `get_operation_property` function.

It is important to note that the operations generated from process-level P3L are a list. This means that every time you call `generate_operation` we will append an operation to the existing list. Currently there is a limit of 20 operations that you can generate for any one part. There is no limit to the number of allowed operations you can specify for a custom process.

To create a custom process, go to the processes page and select "Custom" as the type in the drop down.

Let's dive into the most basic of examples to illustrate how this works. Let's set up a custom process with a few allowed operations and replicate the out-of-the-box behavior from a generic process:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5e9dd8ad2c7d3a7e9aeb451a/file-1kpBIc1Ymh.png)So as you can see, I have added four operations to my allowed list: Material, Grinding, Lathe, and Inspection. Now lets take a look at our operation generation formula by clicking edit formula:

```
for op_name in get_allowed_operations():
  if part.component_type == MANUFACTURED:
      generate_operation(op_name)
```

So we see in the formula above we use the `get_allowed_operations()` iterator function to loop through the names of the allowed operations we specified in the image above. Then we check to see if the part is MANUFACTURED (as opposed to PURCHASED or ASSEMBLED). If the part is in fact a manufactured part, we will generate an operation. So when we apply this process to a non-assembly part, we would expect to see a list of our four operations above.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5e9ddac204286364bc98aa33/file-a6QjXeKX1W.png)Lets build upon our simple formula above and now replicate the assembly and per quote item functionality we get with generic processes as well. First lets add one more operation to our allowed list called "Assemble." Let's say we only want to generate an Assemble op if our part is an assembly, and we only ever want to generate an Inspection op once per quote item. This formula would accomplish just that:

```
if part.component_type == MANUFACTURED:
  generate_operation('Material')
  generate_operation('Grinding')
  generate_operation('Lathe')
elif part.component_type == ASSEMBLED:
  generate_operation('Assemble')

if part.is_root_component:
  generate_operation('Inspection')
```

After the formula above, we can start to see how useful custom processes can become. You can even do things like request geometric interrogations and interact with custom part attributes to influence operation generation. Let's envision a scenario where the outer diameter of a turned part is going to determine which workcenter the part is routed to. Additionally, let's set up this process-level P3L to work with both geometric AND non-geometric files by utilizing custom part attributes. Let's first establish our allowed operation list for our process:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5e9de0372c7d3a7e9aeb45e3/file-8HzA8sXkw7.png)Now let's take a look at our formula for operation generation:

```
units_in()

generate_operation('Material')

lathe = analyze_lathe()
geometric_outer_diameter = lathe.stock_radius * 2
if geometric_outer_diameter:
  set_custom_attribute('outer_diameter', geometric_outer_diameter)

outer_diameter = get_custom_attribute('outer_diameter', 0)
if outer_diameter > 4:
  generate_operation('Large Diameter Lathe')
else:
  generate_operation('Small Diameter Lathe')
```

Let's walk thru the code above. First we generate our Material operation as we know we will need that regardless. Then we request a lathe interrogation to extract the lathe minimum stock radius. If we successfully extract a radius (meaning the part has a good geometric file associated with it) then we store the geometric outer diameter as a custom attribute on the part object. We then immediately get the `outer_diameter` custom part attribute using `get_custom_attribute`. Then based on the value found for our `outer_diameter` we generate either the Large Diameter Lathe or Small Diameter Lathe operation. It is important to note that we use the custom attributes on the part here because it allows this custom op generation to work given user input of the outer diameter. For more information on custom part attributes check out our P3L language features article.

Now let's get a bit more advanced and give an example on how to use the `operation_properties` input to our `generate_operation` function. Let's say you want to track all the times a part is in transit between different workcenters. We can create an operation called Transit that can use an operation property specified in process-level P3L to establish a cost for certain transitions from workcenter to workcenter. Let's say you have a Mill-Turn process where information on the part (or the part itself) needs to move around the shop. It starts in the front office, then goes to programming, then goes to the turning center, then to the mill, then to inspection, and then to shipping. Between each of these workcenters we will generate a "Transit" operation with a specified time. First, here is our list of allowed operations:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5e9de71f2c7d3a7e9aeb466e/file-KhNO0ehbAT.png)And now here is the formula to generate our operations:

```
generate_operation('Admin')

props = {'time': 15}  # transit time in minutes
name = 'Admin to Programming'
generate_operation('Transit', custom_name=name, operation_properties=props)

generate_operation('Programming')

props = {'time': 10}  # transit time in minutes
name = 'Programming to Lathe'
generate_operation('Transit', custom_name=name, operation_properties=props)

generate_operation('Lathe')

props = {'time': 15}  # transit time in minutes
name = 'Lathe to Mill'
generate_operation('Transit', custom_name=name, operation_properties=props)

generate_operation('Mill')

props = {'time': 20}  # transit time in minutes
name = 'Mill to Inspection'
generate_operation('Transit', custom_name=name, operation_properties=props)

generate_operation('Inspection')

props = {'time': 20}  # transit time in minutes
name = 'Inspection to Shipping'
generate_operation('Transit', custom_name=name, operation_properties=props)

generate_operation('Shipping')
```

So we generate our operations as the part would flow through the shop from Admin to Programming to Lathe to Mill to Inspection to Shipping. Between each op, we add a transit op with a custom name and a specified time. Now let's take a look at our Transit operation to see how we use the operation properties:

```
move_time = var('runtime', 0, 'time object is in transit', number, frozen=False)
move_time.update(get_operation_property('time', 0) / 60)
move_time.freeze()

rate = var('Rate', 25, '$/hr', currency)

PRICE = move_time * rate
DAYS = 0
```

And now how it all comes together when we apply the process to a part:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5e9de70b2c7d3a7e9aeb466c/file-PKAwLAb6KO.png)In process-level P3L, you have access to almost all of the language features described in our P3L Language Features article. You however do not have access to the following functions: `var, drop_down_var, variable_group, set_operation_name, get_workpiece_value, set_workpiece_value, get_price_value`. These functions pertain to our operations UI and thus do not really have a place in process-level P3L.

Process-level P3L is a powerful way to customize and streamline your quoting experience. Additionally, it can drastically help streamline routing efforts, particularly as they pertain to any ERP integrations you may want to make/have with Paperless Parts. We highly recommend reaching out to support if you have questions or need help setting up a custom process.
