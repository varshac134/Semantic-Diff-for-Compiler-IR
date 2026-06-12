
int compute(int x, int y) {
    int result = x * 8;
    if (result > 100) {
        result = result + y;
    } else {
        result = result - y;
    }
    return result;
}
