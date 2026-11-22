// What the page remembers between requests.

export const state = {
  analysisId: null,     // the analysis the Save button stores
  lastResult: null,     // the last analysis, for the report
  lastInput: "",        // its URL and file names, for the report
  joined: [],           // campaigns the last analysis joined (highlighted in the groups tab)
  groupNo: new Map(),   // sorted member ids -> K number, from the last groups load
  groupsTau: 0.6,       // tau of the last groups load
  graphTau: null,       // tau the graph was drawn for (null: draw again)
};

export const keyOf = (ids) => [...ids].sort().join("|");
