# DBMS Notes: Transactions and Concurrency

A database must stay correct even when many users are reading and updating it at the same time. Transactions and concurrency-control techniques help make that possible.

## Transactions

A **transaction** is a sequence of database operations treated as one logical unit of work.

Example: transferring money from Account A to Account B.

1. Subtract money from Account A.
2. Add money to Account B.
3. Commit both changes.

If a failure happens after step 1 but before step 2, the database should roll back the entire transaction.

## ACID Properties

The four ACID properties describe reliable transactions.

### Atomicity

Atomicity means a transaction is all-or-nothing. Either all operations succeed, or none of them become permanent.

### Consistency

Consistency means a transaction moves the database from one valid state to another valid state.

For example, a transfer should not create or destroy money.

### Isolation

Isolation means concurrent transactions should not interfere in a way that produces an incorrect result.

### Durability

Durability means a committed transaction remains saved even after a crash or power failure.

## Schedules

A **schedule** is the order in which operations from one or more transactions are executed.

- A **serial schedule** runs one entire transaction before starting the next.
- A **non-serial schedule** interleaves operations from multiple transactions.

Non-serial schedules can improve performance, but they need concurrency control.

## Serializability

A schedule is **serializable** if its effect is equivalent to some serial schedule.

Serializability is important because it lets transactions run concurrently without losing the correctness expected from one-at-a-time execution.

## Common Concurrency Problems

### Lost Update

A lost update occurs when two transactions read the same value, both modify it, and the later write overwrites the earlier one.

### Dirty Read

A dirty read occurs when one transaction reads data written by another transaction that has not committed yet.

### Non-Repeatable Read

A non-repeatable read occurs when a transaction reads the same row twice and gets different values because another transaction committed a change in between.

## Two-Phase Locking

**Two-Phase Locking**, often written as 2PL, is a locking protocol used to help guarantee serializability.

It has two phases:

1. **Growing phase:** a transaction may acquire locks but cannot release them.
2. **Shrinking phase:** a transaction may release locks but cannot acquire new ones.

Strict 2PL keeps exclusive locks until commit or rollback. This prevents other transactions from reading uncommitted changes.

## Deadlock

A **deadlock** happens when transactions wait forever for each other’s locks.

Example:

- Transaction T1 holds a lock on Row A and waits for Row B.
- Transaction T2 holds a lock on Row B and waits for Row A.

The database can handle deadlocks through prevention, avoidance, detection, or timeout-based recovery.

## Quick Revision Checklist

Before an exam, be able to explain:

- what makes a transaction different from a single SQL statement
- each ACID property with a small example
- why serializability matters
- the difference between a dirty read and a lost update
- how Two-Phase Locking works
- how deadlock occurs

## Related Topics

### Functional Dependencies

Functional dependencies are used earlier in relational design to identify how attributes determine one another. Good relation design reduces redundancy before transactions begin operating on the database.

### Normalization

Normalization organizes relations to reduce repeated data and update anomalies. Transaction processing then protects the normalized data when many users access it at once.

