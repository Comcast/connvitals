# Contributing Guidelines
If you would like to contribute code to this project you can do so through
GitHub by forking the repository and sending a pull request.

Please ensure that your contribution does not cause the `pylint` score of the
package to fall below 9.5. You can check the score with

```
pylint /path/to/connvitals/connvitals/
```

You may safely ignore the following errors/warnings (by setting this in your
`~/.pylintrc` file or specifying it on the command line, but please don't
explicitly ignore these with a pylint directive in-line with the code):

* C0103
* C0326
* C0330
* C0362
* C0413
* E1300
* R0902
* R0911
* W0603
* W0612
* W1401

The rest of `pylint`'s settings should remain default except that:

* Indentations should be with **tabs only, NEVER spaces**. Spaces may be used
within an indentation level to align text.
* Line endings should be unix/line-feed (LF)/'\n' only, **don't** include any
Windows line endings (carriage-return-then-linefeed (CRLF)/'\r\n' )
* **All** files in the project **must** end with a newline (leave a blank line
at the end of the file.)

Now some comcast stuff:

## CLA
---------
Before Comcast merges your code into the project you must sign the [Comcast
Contributor License Agreement
(CLA)](https://gist.github.com/ComcastOSS/a7b8933dd8e368535378cda25c92d19a).

If you haven't previously signed a Comcast CLA, you'll automatically be asked
to when you open a pull request. Alternatively, we can send you a PDF that
you can sign and scan back to us. Please create a new GitHub issue to request
a PDF version of the CLA.
