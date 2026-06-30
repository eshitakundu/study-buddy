# DBMS Notes: Relational Design

These notes introduce the rules used to design relational tables that store data cleanly and avoid common update problems.

## Functional Dependencies

A **functional dependency** describes a relationship between attributes in a relation.

We write:

`X → Y`

This means that once the value of `X` is known, the value of `Y` is determined.

### Example

In a student table:

| student_id | student_name | department |
|---|---|---|
| 101 | Asha | CSE |
| 102 | Ravi | ECE |

`student_id → student_name, department`

A student ID identifies exactly one student name and one department.

### Why Functional Dependencies Matter

Functional dependencies help us:

- identify candidate keys
- find repeated or unnecessary data
- detect partial dependencies
- detect transitive dependencies
- decide whether a table should be decomposed

### Common Terms

- **Superkey:** Any attribute set that uniquely identifies a tuple.
- **Candidate key:** A minimal superkey. No attribute can be removed without losing uniqueness.
- **Prime attribute:** An attribute that belongs to at least one candidate key.
- **Non-prime attribute:** An attribute that does not belong to any candidate key.

## Normalization

**Normalization** is the process of organizing a database into well-structured relations.

Its main purpose is to reduce redundancy and prevent anomalies.

### Update Anomaly

An update anomaly happens when the same fact is stored in multiple places and one copy is changed while another is forgotten.

### Insertion Anomaly

An insertion anomaly happens when a fact cannot be stored unless another unrelated fact is also available.

### Deletion Anomaly

A deletion anomaly happens when removing one row accidentally removes another useful fact.

## First Normal Form (1NF)

A relation is in **First Normal Form** when:

1. every attribute contains atomic values
2. there are no repeating groups
3. each row can be uniquely identified

A phone-number column containing `9876, 9123` is not atomic. It should be represented using separate rows or a separate relation.

## Second Normal Form (2NF)

A relation is in **Second Normal Form** when:

1. it is already in 1NF
2. every non-prime attribute depends on the whole candidate key

2NF mainly matters when the candidate key is composite.

### Example

Consider:

`ENROLLMENT(student_id, course_id, student_name, course_name, grade)`

The key is `(student_id, course_id)`.

But:

- `student_id → student_name`
- `course_id → course_name`

These are partial dependencies because `student_name` depends only on `student_id`, and `course_name` depends only on `course_id`.

A better design is:

- `STUDENT(student_id, student_name)`
- `COURSE(course_id, course_name)`
- `ENROLLMENT(student_id, course_id, grade)`

## Third Normal Form (3NF)

A relation is in **Third Normal Form** when:

1. it is already in 2NF
2. non-prime attributes do not depend on other non-prime attributes

3NF removes transitive dependencies.

### Example

`EMPLOYEE(emp_id, emp_name, dept_id, dept_name)`

If:

- `emp_id → dept_id`
- `dept_id → dept_name`

then `emp_id → dept_name` indirectly.

The dependency through `dept_id` is a transitive dependency. A better design is:

- `EMPLOYEE(emp_id, emp_name, dept_id)`
- `DEPARTMENT(dept_id, dept_name)`

## Boyce-Codd Normal Form (BCNF)

A relation is in **Boyce-Codd Normal Form** when, for every non-trivial functional dependency:

`X → Y`

`X` must be a superkey.

BCNF is stricter than 3NF. It removes some redundancy that can remain in a 3NF relation.

## Quick Comparison

| Normal Form | Main Rule | Problem It Addresses |
|---|---|---|
| 1NF | Atomic values, no repeating groups | Repeating data |
| 2NF | No partial dependency on a composite key | Redundancy from part of a key |
| 3NF | No transitive dependency among non-prime attributes | Indirect redundancy |
| BCNF | Every determinant is a superkey | Remaining dependency-based redundancy |


## Transactions

Good relational design and transactions solve different problems. Normalization reduces redundant data in the table design, while transactions protect correct changes to that data during updates.
