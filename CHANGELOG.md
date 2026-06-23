# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Add deallocation functionality to manage order lines in product batches, including functions Product.deallocate, Batch.deallocate, and Batch.can_deallocate for removal and eligibility checks, along with an InvalidDeallocation exception for handling invalid operations. (Product.deallocate, Batch.deallocate)

### Changed

- Update the Product and Batch classes to integrate with the MessageBus for improved handling of batch allocations and deallocations. (model.py, Product)
