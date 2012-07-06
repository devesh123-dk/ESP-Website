Ext.define('LU.Util', {

    singleton: true,

    config: {

        difficultyGrouper: {
            groupFn: function(record) {
                return record.get('hardness_desc');
            },
            sortProperty: 'hardness_rating'         // sorts the grouped headers
        },

        timeGrouper: {
            groupFn: function(record) {
                // formatting syntax: http://docs.sencha.com/ext-js/4-0/#!/api/Ext.Date
                return Ext.Date.format(record.get('section_start_time'), 'g:i A');
            },
            sortProperty: 'section_start_time'
        }
    },

    constructor: function(config) {
        this.initConfig(config);
        this.callParent([config]);
    },

    getStringGrouper: function(property) {
        return {
            groupFn: function(record) {
                return record.get(property)[0];
            },
            sortProperty: property
        };
    },

    getProgram: function() {
        return Ext.getStore('User').first().getProgram();
    },

    getCatalogUrl: function() {
        return '/learn/' + this.getProgram().get('baseUrl') + '/catalog_json';
    },

    getRegisteredClassesUrl: function() {
        return '/learn/' + this.getProgram().get('baseUrl') + '/catalog_registered_classes_json';
    },

    getProgramTitle: function() {
        return this.getProgram().get('title');
    },

    getRegisteredSectionIds: function(store) {

        var temp = [];
        store.clearFilter();
        Ext.Array.each(store.getData().items, function(item, index, list) {
            temp.push(item.get('section_id'));
        });
        return temp;
    },

    getClasses: function(callback) {

        var catalogUrl = this.getCatalogUrl(),
            registeredSectionUrl = this.getRegisteredClassesUrl(),
            classStore = Ext.getStore('Classes'),
            timeStore = Ext.getStore('Timings'),
            registeredSectionStore = Ext.getStore('RegisteredSections'),
            registeredClassStore = Ext.getStore('RegisteredClasses'),
            registeredTimeStore = Ext.getStore('RegisteredTimings');

        // clears any previous existing models
        classStore.removeAll();
        timeStore.removeAll();
        registeredSectionStore.removeAll();
        registeredClassStore.removeAll();
        registeredTimeStore.removeAll();

        // retrieves the registered classes
        registeredSectionStore.setProxy({
            type: 'ajax',
            url: registeredSectionUrl
        });

        var sectionIds;
        registeredSectionStore.load({
            callback: function(records, operation, success) {
                sectionIds = this.getRegisteredSectionIds(registeredSectionStore);
            },
            scope: this
        });

        Ext.Ajax.request({
            url: catalogUrl,
            success: function(result) {

                var data = Ext.JSON.decode(result.responseText);

                // flattens the data received from server
                // i.e. each section will have its individual record
                Ext.Array.each(data, function(classItem, classIndex, classList) {

                    var sections = classItem.get_sections;
                    Ext.Array.each(sections, function(sectionItem, sectionIndex, sectionList) {

                        // section_index is used to derive the class code
                        var classModel = Ext.create('LU.model.Class', Ext.apply(classItem, {section_index: sectionIndex}));

                        classModel.set('id', parseInt('' + classItem.id + sectionItem.id));
                        classModel.set('section_id', sectionItem.id);
                        classModel.set('section_capacity', sectionItem.capacity);
                        classModel.set('section_num_students', sectionItem.num_students);
                        classModel.set('section_duration', sectionItem.duration);
                        classStore.add(classModel);

                        // maps the meeting times to each record
                        var timings = sectionItem.get_meeting_times;
                        Ext.Array.each(timings, function(timeItem, timeIndex, timeList) {

                            // note: currently we only use the first meeting time to perform sorting
                            if (timeIndex == 0) {
                                classModel.set('section_short_description', timeItem.short_description);
                                classModel.set('section_start_time', timeItem.start);
                                classModel.set('section_end_time', timeItem.end);
                            }
                            var timeModel = Ext.create('LU.model.Timing', timeItem);
                            timeModel.set('id', parseInt('' + classModel.get('id') + timeItem.id));
                            timeModel.setClass(classModel.get('id'));
                            timeStore.add(timeModel);

                            if (Ext.Array.contains(sectionIds, classModel.get('section_id'))) {
                                registeredClassStore.add(classModel);
                                registeredTimeStore.add(timeModel);
                            }
                        });
                    });
                });

                callback();
            },
            failure: function(result) {
                callback(result);
            }
        });
    },
});