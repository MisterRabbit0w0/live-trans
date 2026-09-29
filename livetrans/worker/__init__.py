"""Out-of-process model runtime.

Everything except ``client`` must stay importable with only the standard
library, numpy and the model's own packages: an external runtime runs this
package from the app's source tree without installing LiveTrans.
"""
