# Bin Tools Test Suite

This document describes the comprehensive test suite for the `bin/` tools to prevent regressions after refactoring.

## Overview

The `tests/test_bin_tools.py` file contains 16 tests that verify all three programs in `bin/` work correctly:

- **`bin/runner.py`** - Data collection and database management tool
- **`bin/scheduler.py`** - Device monitoring and rules execution tool  
- **`bin/rules.py`** - HVAC control rules definition file

## Test Coverage

### ✅ **Basic Functionality Tests**
- **Help Commands**: Verify `--help` works for all tools
- **Import Tests**: Ensure all required modules can be imported
- **Syntax Validation**: Check that `rules.py` has valid Python syntax
- **File Existence**: Verify all required files exist and are readable

### ✅ **Database Access Tests**
- **Database Connection**: Test that tools can connect to test databases
- **Data Operations**: Verify database read/write operations work
- **Report Generation**: Test database reporting functionality
- **AQI Updates**: Test air quality index database updates

### ✅ **Tool-Specific Tests**

#### **runner.py Tests**
- `test_runner_help` - Verify help output
- `test_runner_database_access` - Test database connectivity
- `test_runner_aqi_update` - Test AQI database updates
- `test_runner_daily_cleanup` - Test daily maintenance functions
- `test_runner_rules_test` - Test rules execution
- `test_runner_with_test_database` - Test with sample data
- `test_runner_with_csv_import` - Test CSV data import

#### **scheduler.py Tests**
- `test_scheduler_help` - Verify help output
- `test_scheduler_dry_run` - Test dry-run mode
- `test_scheduler_verbose` - Test verbose logging
- `test_scheduler_imports` - Test module imports

#### **rules.py Tests**
- `test_rules_file_exists` - Verify file exists
- `test_rules_syntax_valid` - Validate Python syntax

### ✅ **Environment Tests**
- **GitHub Actions**: Simulate CI/CD environment
- **Local Development**: Test in local environment
- **Configuration Handling**: Test with missing config gracefully

## Test Features

### 🔧 **Robust Error Handling**
- Tests handle missing configuration gracefully
- Database connection failures are properly tested
- Missing device mappings are handled appropriately

### 🗄️ **Database Testing**
- Uses temporary databases for isolation
- Tests with both empty and populated databases
- Verifies data integrity and operations

### 🚀 **CI/CD Compatibility**
- Tests work in both local and GitHub Actions environments
- No external dependencies required for basic tests
- Fast execution (all tests complete in ~6 seconds)

## Running the Tests

```bash
# Run all bin tools tests
.venv/bin/python -m pytest tests/test_bin_tools.py -v

# Run specific test
.venv/bin/python -m pytest tests/test_bin_tools.py::TestBinTools::test_runner_help -v

# Run with coverage
.venv/bin/python -m pytest tests/test_bin_tools.py --cov=bin
```

## Test Results

All 16 tests pass successfully:
- ✅ **runner.py**: 7 tests covering all major functionality
- ✅ **scheduler.py**: 4 tests covering device monitoring
- ✅ **rules.py**: 2 tests covering syntax and file validation
- ✅ **Integration**: 3 tests covering environment and consistency

## Benefits

1. **Regression Prevention**: Catches issues when refactoring code
2. **Documentation**: Tests serve as usage examples
3. **CI/CD Safety**: Ensures tools work in automated environments
4. **Development Confidence**: Developers can refactor safely
5. **Quality Assurance**: Validates all tool functionality

## Maintenance

- Add new tests when adding new tool features
- Update tests when changing tool interfaces
- Run tests before any major refactoring
- Include bin tools tests in CI/CD pipeline

This test suite ensures that the `bin/` tools continue to work correctly after any code changes, preventing the issues that occurred during the initial refactoring.
