export const serializeParams = (params: Record<string, any>): string => {
  const searchParams = new URLSearchParams();
  
  for (const key in params) {
    const value = params[key];
    if (value === null || value === undefined) {
      continue;
    }
    if (Array.isArray(value)) {
      for (const item of value) {
        searchParams.append(key, item);
      }
    } 
    else {
      searchParams.append(key, value.toString());
    }
  } 
  return searchParams.toString();
};
