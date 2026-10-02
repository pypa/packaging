# packaging - Online Version & Requirement Validator

This is a web-based tool that allows users to validate and test Python package versions, requirements, and specifiers using the latest `packaging` library from PyPI, running entirely in the browser via Pyodide.

## Features

- **Version Validation**: Parse and validate version strings according to PEP 440
- **Requirement Validation**: Validate requirement strings and extract their components
- **Specifier Validation**: Test version specifiers and check if specific versions match
- **No Installation Required**: Runs entirely in the browser using Pyodide
- **Latest Version**: Always uses the latest packaging library from PyPI

## How to Use

### Local Development

1. Navigate to the `web_validator` directory
2. Open `index.html` in a web browser
3. The tool will automatically load Pyodide and the packaging library
4. Use the tabs to switch between Version, Requirement, and Specifier validators

### Deployment

The validator can be deployed to any static hosting service:

- GitHub Pages
- Netlify
- Vercel
- Any web server that can serve static HTML files

Simply upload the `index.html` file and it will work out of the box.

## Use Cases

This tool is particularly useful for:

1. **Quick Testing**: Quickly test if a version string or requirement is valid without installing the packaging library
2. **Documentation**: Help users understand version and requirement syntax
3. **Debugging**: Debug issues with version comparisons or requirement parsing
4. **Learning**: Learn about PEP 440 version specification and requirement syntax

## Technical Details

### Technology Stack

- **Pyodide**: Python runtime for WebAssembly
- **packaging**: The official Python packaging library from PyPI
- **micropip**: Package installer for Pyodide
- **Vanilla JavaScript**: No external JavaScript dependencies

### How It Works

1. The page loads Pyodide from a CDN
2. Pyodide initializes a Python runtime in the browser
3. micropip installs the latest `packaging` library from PyPI
4. User input is sent to the Python runtime
5. Results are computed using the packaging library
6. Results are displayed in the browser

### Performance Considerations

- Initial load time: ~5-10 seconds (downloads Pyodide and packaging)
- Subsequent validations: Nearly instant
- Caching: Browser caching reduces load times on repeat visits

## Browser Compatibility

Works in all modern browsers that support WebAssembly:

- Chrome/Edge 57+
- Firefox 52+
- Safari 11+
- Opera 44+

## Limitations

- Requires JavaScript to be enabled
- Requires internet connection to load Pyodide and packaging library initially
- Some advanced packaging features may not be available in the browser environment

## Future Enhancements

Potential improvements for the future:

- Add support for marker evaluation
- Add dependency group validation
- Add version comparison tool
- Add requirement file parsing
- Offline support with service workers

## Contributing

This tool is part of the packaging project. For issues or suggestions:

1. File an issue on the [packaging GitHub repository](https://github.com/pypa/packaging/issues)
2. Mention this tool in the issue description

## License

This tool follows the same license as the packaging project (Apache 2.0 / BSD 2-Clause).