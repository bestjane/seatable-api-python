import copy
import datetime
from ply import lex, yacc


class Lexer(object):

    def __init__(self):
        self.lexer = lex.lex(module=self)

    # List of token names. This is always required
    tokens = (
        'LBORDER', 'RBORDER',
        'AND', 'OR',
        'EQUAL', 'NOT_EQUAL', 'GTE', 'GT', 'LTE', 'LT',
        'QUOTE_STRING', 'STRING',
    )

    reserved = {
        'and': 'AND',
        'or': 'OR',
    }

    # Regular expression rules for simple tokens
    t_LBORDER = r'\('
    t_RBORDER = r'\)'
    t_EQUAL = r'='
    t_NOT_EQUAL = r'!=|<>'
    t_GTE = r'>='
    t_GT = r'>'
    t_LTE = r'<='
    t_LT = r'<'

    def t_QUOTE_STRING(self, t):
        r"'([^']*)'"
        t.value = t.value[1:-1]
        return t

    def t_STRING(self, t):
        r'[^=|!|>|<|/(|/)|\s]+'
        t.type = self.reserved.get(t.value, 'STRING')
        return t

    # Define a rule so we can track line numbers
    def t_newline(self, t):
        r'\n+'
        t.lexer.lineno += len(t.value)

    # A string containing ignored characters (spaces and tabs)
    t_ignore = ' \t'
    # t_ignore_COMMENT = r'\#'

    # Error handling rule
    def t_error(self, t):
        raise ValueError('Illegal character!', t.value[0])


class ConditionsParser(object):

    def __init__(self):
        self.yaccer = yacc.yacc(module=self)
        self.lexer = Lexer().lexer

    # Parse
    def parse(self, raw_rows, raw_columns, conditions):
        self.raw_rows = raw_rows
        self.raw_columns = raw_columns
        self.raw_columns_map = {column['name']: column for column in raw_columns}
        # main
        rows = self.yaccer.parse(conditions, lexer=self.lexer)
        return rows

    def _check_column_exists(self, column):
        if column not in self.raw_columns_map:
            raise ValueError('Column not found!', column)

    def _parse_time(self, time_str):
        '''
        transfer the time str into datetime obj and standarize it by UTC
        :param time_str: 2020-1-20 or 2020-1-20 9:30 or 2020-1-20 9:30:28
        :return:
        '''
        time_str_list = time_str.split(' ')
        datetime_obj = None
        if len(time_str_list) == 1:
            ymd = time_str_list[0]
            datetime_obj = datetime.datetime.strptime(ymd, '%Y-%m-%d')
        elif len(time_str_list) == 2:
            h, m, s = 0, 0, 0
            ymd, hms_str = time_str_list
            hms_str_list = hms_str.split(':')
            if len(hms_str_list) == 1:
                h = hms_str_list[0]
            elif len(hms_str_list) == 2:
                h, m = hms_str_list
            elif len(hms_str_list) == 3:
                h, m, s = hms_str_list
            datetime_obj = datetime.datetime.strptime("%s %s" % (
                ymd, "%s:%s:%s" % (h, m, s)), '%Y-%m-%d %H:%M:%S')
        return datetime_obj

    def _exchange_value(self, column_type, value):
        if column_type == 'number':
            if '.' in value:
                value = float(value)
            else:
                try:
                    value = int(value)
                except:
                    value = 0
        elif column_type in ('date', 'ctime', 'mtime'):
            value = self._parse_time(value)
        return value

    def _exchange_cell_value(self, column_type, value):
        if column_type == 'date':
            return self._parse_time(value)
        elif column_type in ('ctime', 'mtime'):
            utc_time = datetime.datetime.strptime(value, '%Y-%m-%dT%H:%M:%S.%f+00:00')
            delta2utc = datetime.datetime.now() - datetime.datetime.utcnow()
            local_time = utc_time + delta2utc
            return local_time
        return value

    def _merge(self, left_rows, condition, right_rows):
        merged_rows = []
        left_rows_id_list = [row['_id'] for row in left_rows]

        if condition.lower() == 'and':
            for row in right_rows:
                if row['_id'] in left_rows_id_list:
                    merged_rows.append(row)

        elif condition.lower() == 'or':
            merged_rows = left_rows
            for row in right_rows:
                if row['_id'] not in left_rows_id_list:
                    merged_rows.append(row)

        return merged_rows

    def _filter(self, column, condition, value):
        self._check_column_exists(column)
        filtered_rows = []
        column_type = self.raw_columns_map[column].get('type')
        value = self._exchange_value(column_type, value)

        if condition == '=':
            for row in self.raw_rows:
                if self._exchange_cell_value(column_type, row.get(column)) == value:
                    filtered_rows.append(row)

        elif condition in ('!=', '<>'):
            for row in self.raw_rows:
                if self._exchange_cell_value(column_type, row.get(column)) != value:
                    filtered_rows.append(row)

        elif condition == '>=':
            for row in self.raw_rows:
                if self._exchange_cell_value(column_type, row.get(column)) >= value:
                    filtered_rows.append(row)

        elif condition == '>':
            for row in self.raw_rows:
                if self._exchange_cell_value(column_type, row.get(column)) > value:
                    filtered_rows.append(row)

        elif condition == '<=':
            for row in self.raw_rows:
                if self._exchange_cell_value(column_type, row.get(column)) <= value:
                    filtered_rows.append(row)

        elif condition == '<':
            for row in self.raw_rows:
                if self._exchange_cell_value(column_type, row.get(column)) < value:
                    filtered_rows.append(row)

        return filtered_rows

    # List of token names. This is always required
    tokens = (
        'AND', 'OR',
        'EQUAL', 'NOT_EQUAL', 'GTE', 'GT', 'LTE', 'LT',
        'QUOTE_STRING', 'STRING',
    )

    def p_merge(self, p):
        """merge : filter AND filter
                 | filter OR filter
                 | merge AND filter
                 | merge OR filter
                 | filter
        """
        if len(p.slice) > 2:
            p[0] = self._merge(p[1], p[2], p[3])
        else:
            p[0] = p[1]

    def p_filter(self, p):
        """filter : factor EQUAL factor
                  | factor NOT_EQUAL factor
                  | factor GTE factor
                  | factor GT factor
                  | factor LTE factor
                  | factor LT factor
        """
        p[0] = self._filter(p[1], p[2], p[3])

    def p_factor(self, p):
        """factor : QUOTE_STRING
                  | STRING
        """
        p[0] = p[1]

    # Error rule for syntax errors
    def p_error(self, p):
        raise ValueError('Syntax error in input!', p.value)


class QuerySet(object):

    def __init__(self, base, table_name):
        self.base = base
        self.table_name = table_name
        self.raw_rows = []
        self.raw_columns = []
        self.conditions = ''
        self.rows = []

    def __str__(self):
        return 'SeaTable Queryset [ %s ]' % self.table_name

    def __iter__(self):
        return iter(self.rows)

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        return self.rows[index]

    def __bool__(self):
        return len(self.rows) > 0

    def _clone(self):
        clone = self.__class__(self.base, self.table_name)
        return clone

    def _execute_conditions(self):
        if self.conditions and self.raw_rows and self.raw_columns:
            # main
            conditions_parser = ConditionsParser()
            rows = conditions_parser.parse(
                copy.deepcopy(self.raw_rows),
                copy.deepcopy(self.raw_columns),
                copy.copy(self.conditions),
            )
            self.rows = rows
        else:
            self.rows = self.raw_rows

    def filter(self, conditions=''):
        """Performs the query and returns a new QuerySet instance.
        :param conditions: str
        :return: queryset
        """
        clone = self._clone()
        clone.raw_rows = copy.deepcopy(self.rows)
        clone.raw_columns = copy.deepcopy(self.raw_columns)
        clone.conditions = conditions
        clone._execute_conditions()
        return clone

    def get(self, conditions=''):
        """Performs the query and returns a single row matching the given keyword arguments.
        :param conditions: str
        :return row: dict
        """
        clone = self._clone()
        clone.raw_rows = copy.deepcopy(self.rows)
        clone.raw_columns = copy.deepcopy(self.raw_columns)
        clone.conditions = conditions
        clone._execute_conditions()
        if len(clone.rows) == 0:
            return None
        else:
            return clone.rows[0]

    def all(self):
        """Returns a new QuerySet that is a copy of the current one.
        :return: queryset
        """
        clone = self._clone()
        clone.raw_rows = copy.deepcopy(self.raw_rows)
        clone.raw_columns = copy.deepcopy(self.raw_columns)
        clone.conditions = copy.copy(self.conditions)
        clone.rows = copy.deepcopy(self.rows)
        return clone

    def update(self, row_data):
        """Updates all elements in the current QuerySet, setting all the given fields to the appropriate values.
        :param row_data: dict
        :return rows: list
        """
        for row in self.rows:
            response = self.base.update_row(self.table_name, row['_id'], row_data)
            row.update(row_data)
        return self.rows

    def delete(self):
        """Deletes the rows in the current QuerySet.
        :return: int
        """
        row_ids = [row['_id'] for row in self.rows]
        response = self.base.batch_delete_rows(self.table_name, row_ids)
        self.rows = []
        return len(row_ids)

    def first(self):
        """Returns the first object of a query, returns None if no match is found.
        :return row: dict
        """
        if self.rows:
            return self.rows[0]
        else:
            return None

    def last(self):
        """Returns the last object of a query, returns None if no match is found.
        :return row: dict
        """
        if self.rows:
            return self.rows[-1]
        else:
            return None

    def count(self):
        """Returns the number of rows as an integer.
        :return: int
        """
        return len(self.rows)

    def exists(self):
        return len(self.rows) > 0
