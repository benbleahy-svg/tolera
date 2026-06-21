---
title: "P3L Lists"
slug: p3l-lists
source: https://help.paperlessparts.com/s/article/p3l-lists
topic: "Pricing, Costing & P3L"
captured: 2026-06-19
---

# P3L Lists

> Source: https://help.paperlessparts.com/s/article/p3l-lists  
> Topic: Pricing, Costing & P3L

You can perform sorting, filtering, and conditional operations on "list-like" objects within your P3L formulas. A "list-like" object in P3L is anything that contains an array of information. These are instances of a P3LList. You can dynamically create these lists using the `create_list` and other helper functions, or interact with built in list objects from other P3L context objects. P3LList objects behave in a very similar fashion to built-in Python 3 lists, but have some functionality removed for the sake of preventing errors and some functionality added to increase usability.

## Cheat Sheet

#### List Creators

`create_list(*args: any) -> P3LList`

Create a new instance of a P3LList based on the **args** input. **args** can be an explicit comma separated list of any type, or it can be another P3LList. If the input is another P3LList, it will create a copy of the P3LList.

#### List Methods

The following functions can be performed on a P3LList object. You call these methods like you would any other Python 3 method, by using the "dot" operator (e.g. `list_object.append('a')`).

`append(item: any) -> P3LList (self)`

Appends the **item** to the P3LList object. This method will modify the instance in place. This method will return the instance you are modifying.

The instance is returned for the sake of chaining multiple list operations together on the same line. This behavior is mirrored with several other list operators that modify the object in place. See usage examples below for more details.

`extend(other_list: P3LList) -> P3LList (self)`

Extend the **other_list** to the P3LList object. This method will modify the instance in place. This method will return the instance you are modifying.

`reverse() -> P3LList (self)`

Reverse the order of the P3LList object. This method will modify the instance in place. This method will return the instance you are modifying.

`copy() -> P3LList (other)`

Create a copy of the P3LList. This method will return an entirely new instance and any operations performed on the copy will not affect the original.

`clear() -> P3LList (self)`

Clears the contents of the P3LList, making it equal to a empty Python list `[]`. This method will modify the instance in place. This method will return the instance you are modifying.

`remove(item: any)`

Will attempt to remove the **item** from the P3LList instance. This method mirrors the built in Python `list.remove(item)` method. This means that if the item is not found within the list, an error will be thrown. To safely use this method, you should make sure the P3LList contains the **item** before removing it using the `in` operator. This method will modify the instance in place.

`pop(index: int = 0)`

Will remove and return the value located at the **index** value from the P3LList instance. **index** defaults to 0 (the first entity in the list). This method mirrors the built in Python `list.pop()` method. This means that if the specified index exceeds the length of the P3LList, an error will be thrown. This method will modify the instance in place.

`sort(lambda_func) -> P3LList (self)`

Sorts the contents of the P3LList based on the **lambda_func**. This method will modify the instance in place. This method will return the instance you are modifying.

Lambda functions are a built in Python concept that allows you to write very simple functions with very little code. Check the usage section below for details on how to use lambda functions with P3LList methods.

`filter(lambda_func) -> P3LList (self)`

Filters the contents of the P3LList based on the **lambda_func**. This method will modify the instance in place. This method will return the instance you are modifying.

`map(lambda_func) -> P3LList (other)`

Returns a new P3LList object containing the values you have created from the **lambda_func** map. This method will not affect the instance and will return an entirely new P3LList instance.

A mapping function will create a new list with a corresponding value for each value in the existing list pertaining to the operator function you provide to the method. Check the usage section below for details on how to use the `map` method.

`reduce(lambda_func, initial=None)`

Reduces the P3LList based on the **lambda_func**. Will pre-apply the **initial** value to the reduction if is not `None`. The **initial** value defaults to `None`.

List reduction is a quick way to collect aggregate values from an array. For example, if you need to collect the sum of all numbers in a list, using `list.reduce(lambda a, b: a + b)` is a fast way to accomplish this without needing to explicitly iterate over the list object. Check the usage section for details on how to use P3LList reduce.

`unique(lambda_func) -> P3LList (other)`

Returns a new list composed of the first instance of each element in the list whose extracted value (retrieved by the supplied **lambda_func**) is unique.

List uniqueness is a great way to find unique features by properties, i.e. find all of the types of holes in a milled part.

#### `join(delimiter: str = "\n") -> str`

Join all elements in the array into a string, separated by the specified **delimiter,**which defaults to a newline ("\n") character.

List joining with newline is the best way to compose multi-line operation notes.

#### List Helpers

`create_multi_sort(*args)`

Returns an object that a lambda function can use to sort a P3LList by multiple conditions. **args** is a comma separated list of inputs that reference the target variable of a lambda function. For example, to sort a list of pocket features by more than one property, use `create_multi_sort` as follows: `get_features(mill3, name='pocket').sort(lambda x: create_multi_sort(-x.properties.volume, -x.properties.area))`.

`iterate(list_object: P3LList)`

General helper function to allow you to iterate over any P3LList object. See usage below for more details.

## Usage

The code block below will demonstrate basic usage for all the functions and methods explained above. The outputs of all operations will be communicated as to what they would look like in standard Python 3 list format.

```
# create a basic list
l1 = create_list('a', 'b', 'c', 'd')
# l1 == ['a', 'b', 'c', 'd']

# perform in operator
'a' in l1  # True
'e' in l1  # False

# append an item to the list
l1.append('e')
# l1 == ['a', 'b', 'c', 'd', 'e']

# extend the list
l1.extend(create_list('f', 'g'))
# l1 == ['a', 'b', 'c', 'd', 'e', 'f', 'g']

# copy the list
l2 = l1.copy()
# l2 == ['a', 'b', 'c', 'd', 'e', 'f', 'g']

# reverse the new list
l2.reverse()
# l1 == ['a', 'b', 'c', 'd', 'e', 'f', 'g']
# l2 == ['g', 'f', 'e', 'd', 'c', 'b', 'a']

# clear the new list
l2.clear()
# l1 == ['a', 'b', 'c', 'd', 'e', 'f', 'g']
# l2 == []

# remove a list item
l1.remove('a')
# l1 == ['b', 'c', 'd', 'e', 'f', 'g']

# attempting to remove an entity not in the list will throw an error, so use this pattern
if 'h' in l1:
  l1.remove('h')
# l1 == ['b', c', 'd', 'e', 'f', 'g']

# pop an index
x = l1.pop()
# l1 == ['c', 'd', 'e', 'f', 'g']
# x == 'b'

# create a basic numeric list
l1 = create_list(0, 1, 2, 3, 4, 5)

# perform math operations on list
a = max(l1)  # a == 5
b = min(l1)  # b == 0
c = mean(l1)  # c == 2.5
d = median(l1)  # d == 2.5

# sort list in reverse order
l1.sort(lambda x: -x)
# l1 == [5, 4, 3, 2, 1, 0]

# filter list based on condition
l1.filter(lambda x: x > 1)
# l1 == [5, 4, 3, 2]

# sum the list using reduce
total = l1.reduce(lambda a, b: a + b)  # total == (5 + 4 + 3 + 2) == 14
total = l1.reduce(lambda a, b: a + n, initial=10)  # total = 10 + (5 + 4 + 3 + 2) == 19

# create a list of dictionary objects
l1 = create_list(
  {'a': 2, 'b': 1},
  {'a': 2, 'b': 2},
  {'a': 4, 'b': 3},
  {'a': 4, 'b': 4},
)

# create a mapping of the list to just extract the 'b' value
l2 = l1.map(lambda x: x['b'])
# l2 == [3, 4, 1, 2)

# perform a mult-sort operation on list of dictionaries
l1.sort(lambda x: create_multi_sort(-x.a, x.b))
# l1 == [
#  {'a': 4, 'b': 3},
#  {'a': 4, 'b': 4},
#  {'a': 2, 'b': 1},
#  {'a': 2, 'b': 2},
# ]

# perform chained operations, copy initial list to leave it unaffected
l2 = l1.copy().reverse().sort(lambda x: x['a']).map(lambda x: x['b']).sort(lambda x: x)
# l2 == [1, 2, 3, 4]

# iterate over any p3l list
iterator_total = 0
for value in iterate(l2):
  iterator_total += value

reduce_total = l2.reduce(lambda a, b: a + b)
# iterator_total == reduce_total == 10

# GET CREATIVE
# find all sheet metal bends, curls, open_hems, tear_drops, and offsets with length greater than 10 sorted by length and radius
sm = analyze_sheet_metal()
# collect list of all features
features = get_features(sm)
# can also collect features by calling:
features = sm.features  # NOTE: this returns a copy of the features list
# now collect all features with names we care about
features.filter(lambda x: x.name in create_list('bend', 'curl', 'open_hem', 'tear_drop', 'offset'))
# filter list with length greater than 10
features.filter(lambda x: x.properties.length > 10)
# sort list to get longest lengths first, then largest radius)
features.sort(lambda x: create_multi_sort(-x.properties.length, -x.properties.radius))
# iterate thru your features list to perform custom logic
for bf in iterate(features):
  do_something_fun = 1

# now lets construct that same list all in one shot
features = sm.features.filter(
  lambda x: x.name in create_list('bend', 'curl', 'open_hem', 'tear_drop', 'offset') and x.properties.length > 10
).sort(
  lambda x: create_multi_sort(-x.properties.length, -x.properties.radius)
)
```

Lists are an incredibly useful data structure that can streamline your pricing formulas and open up even more ways to accomplish custom pricing logic. List functionality is particularly useful when interacting with table lookups and drop down variables. Be sure to check out those sections to see how you can leverage p3l list functionality to create things like custom dynamic selection forms and application of toolsets to different types of features.
